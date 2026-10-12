"""
Trusted facts for the claim check (symbolic side).

Every fact comes from data we hold ourselves: the institution registry, the student's
own payment history, the institution's approved policy and the scam advisory. Nothing
here is ever read from the document being checked.
"""

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.claims.schema import Claim
from app.documents.index import knowledge_passages
from app.models import Institution, Payee, User
from app.rules.engine import Fact

# A clause of an institution's policy -> the policy facts it states.
POLICY_CLAUSES = {
    "no-agents-no-discounts": ("no_payment_agents", "no_third_party_discounts"),
    "no-visa-threats": ("never_threatens_visa",),
}
# A clause of the scam advisory -> the scam pattern it describes.
ADVISORY_CLAUSES = {
    "fake-agents": "third_party_fee_discount",
    "urgency": "deadline_pressure",
    "threats": "visa_threat",
    "secrecy": "secrecy_request",
}
OFFICIAL_CHANNEL_CLAUSE = "official-channel"

# Claim types whose first argument names an institution or a payee, to be matched to the registry.
_NAMED = {"represents_institution": "institution_name", "agent_of_institution": "institution_name", "payee_name": "name"}
# Claim types the rules match with their argument; every other type is matched by its presence alone.
_WITH_ARGUMENT = {**_NAMED, "payee_account": "account", "payee_bank": "bank", "threat": "kind"}


def digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def acronym(name: str) -> str:
    """ "Shenzhen Polytechnic International University" -> "SPIU"."""
    return "".join(word[0] for word in name.split() if word[:1].isupper())


def _key(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


def aliases(institutions: list[Institution]) -> dict[str, str]:
    """Every way an institution is written (name, local name, acronym) -> its registered name."""
    known: dict[str, str] = {}
    for institution in institutions:
        for alias in (institution.name, institution.name_local, acronym(institution.name)):
            if alias:
                known[_key(alias)] = institution.name
    return known


def collect(session: Session, user: User) -> list[Fact]:
    """Every trusted fact the rules may use, each with where it comes from."""
    institutions = list(session.scalars(select(Institution).order_by(Institution.id)))
    by_acronym = {acronym(item.name).casefold(): item.name for item in institutions}
    facts: list[Fact] = []

    def add(source: str, *atom: str) -> None:
        facts.append(Fact(tuple(atom), "trusted", source))

    for institution in institutions:
        add("Institution registry", "registered_institution", institution.name)
        add("Institution registry", "official_account", institution.name, digits(institution.official_account_ref))

    paid = select(Payee).where(Payee.user_id == user.id, Payee.first_paid_at.is_not(None)).order_by(Payee.id)
    for payee in session.scalars(paid):
        add("Your payment history", "paid_before", payee.name, digits(payee.account_ref))

    seen: set[tuple[str, ...]] = set()
    for passage in knowledge_passages():
        if passage.source == "policy":
            # "spiu_payment_policy_en.md" is the policy of the institution whose acronym is SPIU.
            institution = by_acronym.get(passage.file.split("_")[0].casefold())
            if institution is None:
                continue
            source = f"{acronym(institution)} payment policy"
            found = [("policy", institution, name) for name in POLICY_CLAUSES.get(passage.clause or "", ())]
            if passage.clause == OFFICIAL_CHANNEL_CLAUSE:
                found.append(("official_channel", institution, "official account or student portal"))
        elif passage.source == "advisory" and passage.clause in ADVISORY_CLAUSES:
            source, found = "Scam advisory", [("known_scam_pattern", ADVISORY_CLAUSES[passage.clause])]
        else:
            continue
        for atom in found:  # the same clause exists once per language
            if atom not in seen:
                seen.add(atom)
                add(source, *atom)
    return facts


def ground(claims: list[Claim], session: Session) -> list[Fact]:
    """
    The claims as facts the rules can match. Plain normalisation, no judgement: an
    institution or payee name is replaced by its registered name when it is one of that
    institution's known spellings, and an account number is reduced to its digits.
    """
    known = aliases(list(session.scalars(select(Institution).order_by(Institution.id))))
    grounded: list[Fact] = []
    for position, claim in enumerate(claims):
        argument = _WITH_ARGUMENT.get(claim.type)
        if argument is None:
            atom: tuple[str, ...] = (claim.type,)
        else:
            value = claim.args.get(argument, "")
            if claim.type in _NAMED:
                value = known.get(_key(value), re.sub(r"\s+", " ", value).strip())
            elif claim.type == "payee_account":
                value = digits(value)
            atom = (claim.type, value)
        grounded.append(Fact(atom, "claim", ref=position))
    return grounded


def as_json(fact: Fact) -> dict[str, Any]:
    return {"atom": list(fact.atom), "source": fact.source}
