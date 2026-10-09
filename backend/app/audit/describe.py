"""Readable labels and one-line summaries for audit entries. Fixed text, built by code."""

from typing import Any

from app.money import MINOR_UNITS, format_amount

EVENT_LABELS = {
    "system.genesis": "Log started",
    "system.reset": "Demo reset",
    "document.uploaded": "Document uploaded",
    "document.flagged": "Document flagged",
    "agent.proposed": "Agent proposed",
    "agent.declined": "Agent declined",
    "policy.verdict": "Policy verdict",
    "user.confirmed": "Confirmed",
    "user.otp_failed": "Wrong code",
    "user.otp_verified": "Code verified",
    "user.cancelled": "Cancelled",
    "action.executed": "Executed",
    "action.refused": "Refused",
    "action.expired": "Expired",
}

TOOL_LABELS = {
    "get_balances": "Get balances",
    "get_transactions": "Get transactions",
    "read_document": "Read document",
    "get_fx_rate": "Get FX rate",
    "get_transfer_quote": "Get transfer quote",
    "verify_payee": "Verify payee",
    "explain_decision": "Explain decision",
    "respond_to_user": "Reply",
    "analyse_spending": "Analyse spending",
    "plan_funding": "Plan funding",
    "pay_bill": "Pay bill",
    "convert_currency": "Convert currency",
    "add_payee": "Add payee",
}

TIER_LABELS = {"T0": "Tier 0", "T1": "Tier 1", "T2": "Tier 2", "T3": "Tier 3", "REFUSED": "Refused"}


def event_label(event_type: str) -> str:
    return EVENT_LABELS.get(event_type, event_type)


def _amount(payload: dict[str, Any]) -> str | None:
    """The first amount with a currency found in the payload or one level down."""
    for holder in (payload, *(value for value in payload.values() if isinstance(value, dict))):
        amount, currency = holder.get("amount_minor"), holder.get("currency") or holder.get("from_currency")
        if isinstance(amount, int) and currency in MINOR_UNITS:
            return format_amount(amount, currency)
    return None


def summarise(event_type: str, payload: Any) -> str:
    """A short line saying what the entry is about."""
    if not isinstance(payload, dict):
        return ""
    if event_type == "system.genesis":
        return "Start of the chain"
    if event_type == "system.reset":
        return f"Demo date {payload.get('demo_today')} · FX {payload.get('fx_source')}"

    parts: list[str] = []
    if "action_id" in payload:
        parts.append(f"Action #{payload['action_id']}")
    if "tool" in payload:
        parts.append(TOOL_LABELS.get(payload["tool"], str(payload["tool"])))
    amount = _amount(payload)
    if amount:
        parts.append(amount)
    if "tier" in payload:
        parts.append(TIER_LABELS.get(payload["tier"], str(payload["tier"])))
    reasons = payload.get("reasons") or []
    if reasons:
        more = f" +{len(reasons) - 1} more" if len(reasons) > 1 else ""
        parts.append(f"{reasons[0]}{more}")
    if "attempt" in payload:
        parts.append(f"attempt {payload['attempt']} of {payload.get('max_attempts')}")
    if payload.get("cause") == "otp_attempts_exhausted":
        parts.append("too many wrong codes")
    return " · ".join(parts)
