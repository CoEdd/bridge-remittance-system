"""
The permission tiers and the safeguards, in words, for the Security page.

Built from the policy engine's own tables (BASE_TIERS and the reasons registry), so
what the page shows cannot drift from what the engine does.
"""

from typing import Any

from app.audit.describe import TOOL_LABELS
from app.models import User
from app.policy import BASE_TIERS
from app.policy.reasons import REASONS, Reason

TIER_RULES: dict[str, tuple[str, str]] = {
    "T0": ("Read", "Runs automatically. Nothing changes."),
    "T1": ("Suggest", "Runs automatically. It only proposes."),
    "T2": ("Confirm", "You confirm the exact amount, currency and payee."),
    "T3": ("Step-up", "You confirm and enter a one-time code."),
    "REFUSED": ("Refused", "Never runs. The reasons are shown and logged."),
}

# One line per safeguard, with the reason codes it produces.
SAFEGUARDS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "payee_verification",
        "Payee verification",
        "The account is checked against the one the institution has registered.",
        ("PAYEE_NOT_OFFICIAL",),
    ),
    (
        "changed_details",
        "Changed-details detection",
        "An invoice whose bank details differ from the registered ones is refused.",
        ("BANK_DETAILS_CHANGED",),
    ),
    (
        "scam_patterns",
        "Scam patterns",
        "Agent discounts, urgency, threats and secrecy are matched against known fee scams.",
        ("THIRD_PARTY_DISCOUNT", "SCAM_PATTERN"),
    ),
    (
        "injection_detection",
        "Injection detection",
        "Hidden or AI-addressed text makes a document untrusted. Nothing is paid from it.",
        ("UNTRUSTED_DOCUMENT",),
    ),
    (
        "money_mule",
        "Money-mule detection",
        "Forwarding money that a stranger has just sent is refused.",
        ("MONEY_MULE_PATTERN",),
    ),
    (
        "recheck_at_execution",
        "Re-check at execution",
        "The policy is checked again right before money moves, not only when it is proposed.",
        ("QUOTE_CHANGED", "INSUFFICIENT_FUNDS", "DAILY_LIMIT"),
    ),
    (
        "audit_log",
        "Hash-chained audit log",
        "Every step is logged, and changing any entry breaks the chain from that point on.",
        (),
    ),
)


def _named(reason: Reason) -> dict[str, str]:
    return {"code": reason.code, "title": reason.title["en"]}


def describe_tiers() -> list[dict[str, Any]]:
    """T0 to T3 and Refused: the rule, the tools that start there, and what raises an action to it."""
    rows = []
    for tier, (name, rule) in TIER_RULES.items():
        if tier == "REFUSED":
            raised_by = [reason for reason in REASONS.values() if reason.severity == "block"]
        elif tier == "T3":
            raised_by = [reason for reason in REASONS.values() if reason.requires]
        else:
            raised_by = []
        rows.append(
            {
                "tier": tier,
                "name": name,
                "rule": rule,
                "tools": [
                    {"name": tool, "label": TOOL_LABELS.get(tool, tool)}
                    for tool, base in BASE_TIERS.items()
                    if base == tier
                ],
                "raised_by": [_named(reason) for reason in raised_by],
            }
        )
    return rows


def describe_limits(user: User, cooling_off_seconds: int) -> list[dict[str, Any]]:
    """The student's limits. What happens above each one is read from the reason it raises."""

    def effect(code: str) -> str:
        return "Refused above this" if REASONS[code].severity == "block" else "One-time code above this"

    amounts = (
        ("per_payment", "Per payment", user.per_txn_limit_minor, "OVER_TXN_LIMIT"),
        ("daily_outbound", "Daily outbound", user.daily_limit_minor, "DAILY_LIMIT"),
        ("new_payee", "New payee", user.new_payee_limit_minor, "NEW_PAYEE_LIMIT"),
    )
    return [
        *(
            {"key": key, "label": label, "amount_minor": amount, "seconds": None, "effect": effect(code)}
            for key, label, amount, code in amounts
        ),
        {
            "key": "cooling_off",
            "label": "Cooling-off",
            "amount_minor": None,
            "seconds": cooling_off_seconds,
            "effect": "Wait before a first payment runs",
        },
    ]


def describe_safeguards() -> list[dict[str, Any]]:
    return [
        {"key": key, "title": title, "text": text, "reasons": [_named(REASONS[code]) for code in codes]}
        for key, title, text, codes in SAFEGUARDS
    ]
