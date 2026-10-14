"""
Risk signals for a document. Fixed rules over the extracted fields and the visible
text; the policy engine refuses any payment whose document carries one of them.

Each signal keeps its evidence: the matched text and, for THIRD_PARTY_DISCOUNT, the
clause of the institution's own policy, found by cross-language retrieval.
"""

import re
from collections.abc import Callable, Sequence
from typing import Any

from app.documents.concepts import CONCEPTS, NEGATION
from app.documents.extract import Field, digits_of
from app.documents.index import Hit, knowledge_passages
from app.models import Institution, Payee
from app.sources import ApprovedPattern

Search = Callable[[str, int, str | None], list[Hit]]

# A full stop ends a sentence only when white space follows, so "12,000.00" stays whole.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])|\n+")

SCAM_CATEGORIES = ("urgency", "threat", "secrecy")
# A warning that mentions a threat ("we never threaten your visa") is not itself a threat.
_NEGATABLE = ("threat",)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_END.split(text) if part and part.strip()]


def _same_name(left: str, right: str) -> bool:
    return left.strip().casefold() == right.strip().casefold()


def assess(
    visible_text: str,
    fields: dict[str, Field],
    institutions: list[Institution],
    payees: list[Payee],
    search: Search,
    patterns: Sequence[ApprovedPattern] = (),
) -> list[dict[str, Any]]:
    """
    Every risk signal the document carries, each with its evidence. `patterns` are the
    approved scam patterns from rule sources; their example phrases count like the fixed words.
    """
    signals: list[dict[str, Any]] = []
    payee_name = fields.get("payee_name")
    account = fields.get("payee_account")
    sentences = _sentences(visible_text)
    claimed = next(
        (item for item in institutions if item.name in visible_text or item.name_local in visible_text), None
    )

    # The document speaks for a registered institution, but the money goes elsewhere.
    if claimed and account:
        is_institution = payee_name is not None and (
            _same_name(payee_name.value, claimed.name) or _same_name(payee_name.value, claimed.name_local)
        )
        official = digits_of(account.value) == digits_of(claimed.official_account_ref)
        if not is_institution and not official:
            signals.append(
                {
                    "code": "PAYEE_NOT_OFFICIAL",
                    "evidence": [item.source for item in (payee_name, account) if item],
                    "institution": claimed.name,
                    "payee_name": payee_name.value if payee_name else None,
                    "payee_account": account.value,
                    "official_account": claimed.official_account_ref,
                }
            )

    # A payee paid before, now with a different account.
    if payee_name and account:
        local_names = {item.name: item.name_local for item in institutions}
        for known in payees:
            names = (known.name, local_names.get(known.name, known.name))
            if known.first_paid_at is None or not any(_same_name(payee_name.value, name) for name in names):
                continue
            if digits_of(known.account_ref) != digits_of(account.value):
                signals.append(
                    {
                        "code": "BANK_DETAILS_CHANGED",
                        "evidence": [account.source],
                        "payee_name": known.name,
                        "known_account": known.account_ref,
                        "document_account": account.value,
                    }
                )
                break

    # An offer to pay fees through an agent or third party at a discount.
    offers = [sentence for sentence in sentences if not NEGATION.search(sentence)]
    agent = [sentence for sentence in offers if CONCEPTS["agent"].search(sentence)]
    discount = [sentence for sentence in offers if CONCEPTS["discount"].search(sentence)]
    if agent and discount:
        evidence = list(dict.fromkeys([*agent, *discount]))
        signal: dict[str, Any] = {"code": "THIRD_PARTY_DISCOUNT", "evidence": evidence}
        if claimed:
            hits = search(" ".join(evidence), 1, "policy")
            if hits:
                clause = hits[0].passage
                signal["policy_clause"] = {
                    "text": clause.text,
                    "title": clause.title,
                    "file": clause.file,
                    "language": clause.language,
                    "clause": clause.clause,
                    "score": hits[0].score,
                    "similarity": hits[0].similarity,
                    "shared_concepts": hits[0].shared_concepts,
                    "institution": claimed.name,
                    # The same clause in each language the policy is published in.
                    "versions": {
                        twin.language: {"text": twin.text, "title": twin.title, "file": twin.file}
                        for twin in knowledge_passages()
                        if twin.source == "policy" and twin.clause == clause.clause
                    },
                }
        signals.append(signal)

    # Urgency, threats or secrecy.
    matches: list[dict[str, str]] = []
    for category in SCAM_CATEGORIES:
        for sentence in sentences:
            found = CONCEPTS[category].search(sentence)
            if found and not (category in _NEGATABLE and NEGATION.search(sentence.replace(found.group(0), ""))):
                matches.append({"category": category, "text": found.group(0), "sentence": sentence})
                break
    for pattern in patterns:
        hit = next(
            (
                (example, sentence)
                for example in pattern.examples
                for sentence in sentences
                if example.casefold() in sentence.casefold()
                and not NEGATION.search(sentence.casefold().replace(example.casefold(), ""))
                and all(match["sentence"] != sentence for match in matches)
            ),
            None,
        )
        if hit:
            matches.append({"category": pattern.name, "text": hit[0], "sentence": hit[1], "source": pattern.title})
    if matches:
        signals.append(
            {
                "code": "SCAM_PATTERN",
                "evidence": list(dict.fromkeys(match["sentence"] for match in matches)),
                "categories": [match["category"] for match in matches],
                "matches": matches,
            }
        )

    return signals
