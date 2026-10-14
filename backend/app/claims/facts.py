"""
Trusted facts for the claim check (symbolic side).

Every fact comes from data we hold ourselves: the institution registry, the student's
own payment history, and the rule-source items a person has approved (institution policies
and scam patterns, each with its source sentence). Nothing here is ever read from the
document being checked, and an item that is not approved is never a fact.
"""

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.claims.schema import Claim
from app.models import Institution, Payee, User
from app.rules.engine import Fact
from app.sources.vocabulary import Citation, item_atom

REGISTRY = Citation("Institution registry")
HISTORY = Citation("Your payment history")

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
    """
    Every trusted fact the rules may use. Each carries its citations in `ref`: one per
    source that backs it, so a fact approved from two sources cites both.
    """
    from app.sources import approved_items, citation  # rule sources read this module's name matching

    cited: dict[tuple[str, ...], list[Citation]] = {}

    def add(cite: Citation, *atom: str) -> None:
        cited.setdefault(tuple(atom), []).append(cite)

    for institution in session.scalars(select(Institution).order_by(Institution.id)):
        add(REGISTRY, "registered_institution", institution.name)
        add(REGISTRY, "official_account", institution.name, digits(institution.official_account_ref))

    paid = select(Payee).where(Payee.user_id == user.id, Payee.first_paid_at.is_not(None)).order_by(Payee.id)
    for payee in session.scalars(paid):
        add(HISTORY, "paid_before", payee.name, digits(payee.account_ref))

    for item in approved_items(session):
        add(citation(item), *item_atom(item))
    return [Fact(atom, "trusted", cites[0].title, ref=tuple(cites)) for atom, cites in cited.items()]


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


def cites(fact: Fact) -> tuple[Citation, ...]:
    return fact.ref if fact.kind == "trusted" and isinstance(fact.ref, tuple) else ()


def as_json(fact: Fact) -> dict[str, Any]:
    from app.claims.words import cite_json

    return {"atom": list(fact.atom), "source": fact.source, "cites": [cite_json(cite) for cite in cites(fact)]}
