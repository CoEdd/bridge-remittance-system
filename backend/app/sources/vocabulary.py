"""
The fixed vocabulary of rule items. Claude may only propose items of these shapes; anything
else is dropped. A person can edit an item, but only within the same vocabulary.

- official_account(I, A): institution I collects fees into account A.
- official_channel(I, C): institution I takes payment only through channel C.
- policy(I, P): institution I states policy P about itself.
- known_scam_pattern(N): a scam pattern a published warning describes.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from app.models import Institution, SourceItem

PREDICATES = ("official_account", "official_channel", "policy", "known_scam_pattern")
POLICIES = ("no_payment_agents", "no_third_party_discounts", "never_threatens_visa")
PATTERNS = (
    "third_party_fee_discount",
    "deadline_pressure",
    "visa_threat",
    "secrecy_request",
    "personal_account_request",
    "changed_account_details",
    "money_mule_forwarding",
)
LABELS = {
    "official_account": "Official account",
    "official_channel": "Official channel",
    "policy": "Institution policy",
    "known_scam_pattern": "Scam pattern",
}
# Short names for the edit form.
POLICY_LABELS = {
    "no_payment_agents": "Never uses payment agents",
    "no_third_party_discounts": "No discounts through third parties",
    "never_threatens_visa": "Never threatens a visa",
}
PATTERN_LABELS = {
    "third_party_fee_discount": "Discount for paying a third party",
    "deadline_pressure": "Pressure to pay fast",
    "visa_threat": "Visa threat",
    "secrecy_request": "Request for secrecy",
    "personal_account_request": "Pay into a personal account",
    "changed_account_details": "Account has changed",
    "money_mule_forwarding": "Forward money for a stranger",
}
MAX_SENTENCE = 600
MAX_EXAMPLES = 5
MAX_EXAMPLE = 80  # characters


class Invalid(ValueError):
    """An item outside the vocabulary, or one its source does not back."""


@dataclass(frozen=True)
class Candidate:
    """One proposed item, before it is checked and stored."""

    predicate: str
    institution: str  # "" for a scam pattern
    value: str
    sentence: str
    description: str = ""
    examples: tuple[str, ...] = field(default=())
    confidence: float | None = None


@dataclass(frozen=True)
class Citation:
    """Where a trusted fact comes from, and who approved it."""

    title: str
    domain: str | None = None
    url: str | None = None
    reviewer: str | None = None
    approved_at: datetime | None = None


def flat(text: str) -> str:
    """Text with every run of whitespace made one space: what "word for word" compares."""
    return " ".join(text.split())


def digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def atom_of(predicate: str, institution: str, value: str) -> tuple[str, ...]:
    """The fact the rules see."""
    if predicate == "known_scam_pattern":
        return (predicate, value)
    if predicate == "official_account":
        return (predicate, institution, digits(value))
    return (predicate, institution, value)


def item_atom(item: SourceItem) -> tuple[str, ...]:
    return atom_of(item.predicate, item.institution, item.value)


def _on_domain(host: str, domain: str) -> bool:
    return bool(domain) and (host == domain or host.endswith(f".{domain}"))


def check(
    candidate: Candidate,
    institutions: list[Institution],
    *,
    text: str | None,
    source_domain: str | None,
    fetched: bool,
) -> Candidate:
    """
    The candidate in its stored form, or Invalid with the reason. `text` is the source's
    readable text (None on an edit: the sentence does not change then). `fetched` is true for
    a page fetched from the web, whose domain must belong to any institution it states facts about.
    """
    from app.claims.facts import aliases  # the same name matching as the claim check

    predicate = candidate.predicate
    if predicate not in PREDICATES:
        raise Invalid(f"{predicate!r} is not in the vocabulary.")
    sentence = flat(candidate.sentence)
    if not sentence or len(sentence) > MAX_SENTENCE:
        raise Invalid("The item needs one source sentence.")
    if text is not None and sentence not in flat(text):
        raise Invalid("The sentence is not in the source word for word.")

    value = flat(candidate.value)
    institution = ""
    description = flat(candidate.description)
    # Example phrases are only hints for the keyword layer: odd ones are left out, the item stays.
    examples = tuple(
        dict.fromkeys(flat(example) for example in candidate.examples if 4 <= len(flat(example)) <= MAX_EXAMPLE)
    )[:MAX_EXAMPLES]
    if predicate == "known_scam_pattern":
        if value not in PATTERNS:
            raise Invalid(f"{value!r} is not a known scam pattern name.")
        if not description or len(description) > 200:
            raise Invalid("A scam pattern needs a one-line description.")
    else:
        registered = aliases(institutions).get(" ".join(candidate.institution.split()).casefold())
        if registered is None:
            raise Invalid(f"{candidate.institution!r} is not a registered institution.")
        owner = next(item for item in institutions if item.name == registered)
        if fetched and not _on_domain(source_domain or "", owner.domain):
            raise Invalid(f"Only {owner.domain or 'its own site'} may state facts about {registered}.")
        institution = registered
        if predicate == "policy" and value not in POLICIES:
            raise Invalid(f"{value!r} is not a known policy.")
        if predicate == "official_account" and (len(digits(value)) < 6 or digits(value) not in digits(sentence)):
            raise Invalid("The account number must be in the sentence.")
        if predicate == "official_channel" and not 0 < len(value) <= 80:
            raise Invalid("The channel needs a few words.")
        description, examples = "", ()
    return Candidate(predicate, institution, value, sentence, description, examples, candidate.confidence)
