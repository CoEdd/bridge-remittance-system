"""
The claim schema: the contract between the LLM (neural side) and the rules (symbolic side).

A claim is something the document asserts: its type, its arguments, and the exact
substring of the document it was read from. The LLM may only produce these types.
"""

from dataclasses import asdict, dataclass, field
from typing import Any

# type -> the names of its arguments
CLAIM_TYPES: dict[str, tuple[str, ...]] = {
    "represents_institution": ("institution_name",),  # the sender says they are the institution
    "agent_of_institution": ("institution_name",),  # the sender says they act for the institution
    "payee_name": ("name",),
    "payee_account": ("account",),
    "payee_bank": ("bank",),
    "amount": ("value", "currency"),
    "due": ("date",),  # YYYY-MM-DD, or "today"
    "fee_discount": ("description",),  # an offer to pay fees for less
    "pays_via_third_party": (),  # the money goes to someone other than the institution
    "deadline_pressure": ("description",),  # "today only", "within 2 hours"
    "threat": ("kind",),  # visa, deportation, arrest, expulsion, account_freeze
    "secrecy_request": (),  # "don't tell the finance office"
    "account_change_notice": (),  # "our account has changed"
}
THREAT_KINDS = ("visa", "deportation", "arrest", "expulsion", "account_freeze")


@dataclass
class Claim:
    type: str
    args: dict[str, str] = field(default_factory=dict)
    source: str = ""  # the exact substring of the document
    start: int = 0
    end: int = 0

    def as_json(self) -> dict[str, Any]:
        return asdict(self)


# What Claude must return: every claim as {type, value, detail, source}. `value` is the
# first argument and `detail` the second (only "amount" has one: the currency).
EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(CLAIM_TYPES)},
                    "value": {"type": "string"},
                    "detail": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["type", "value", "detail", "source"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}


def claim_from_answer(item: dict[str, Any]) -> Claim | None:
    """One item of Claude's answer as a claim, or None when it does not fit the schema."""
    names = CLAIM_TYPES.get(str(item.get("type")))
    if names is None:
        return None
    values = [str(item.get("value") or "").strip(), str(item.get("detail") or "").strip()]
    args = {name: value for name, value in zip(names, values)}
    if any(not value for value in args.values()):
        return None
    return Claim(type=str(item["type"]), args=args, source=str(item.get("source") or ""))
