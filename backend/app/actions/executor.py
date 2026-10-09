"""
The executor: the ONLY place that posts user money to the ledger.

It re-runs the policy engine right before posting (time of check equals time of
use). If the verdict is now a refusal, or now needs a step the student has not
completed, nothing is posted.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app import audit
from app.ledger import conversion_legs, payment_legs, post
from app.models import Bill, Payee, PendingAction, User
from app.policy import TIER_RANK, Context, Verdict, evaluate
from app.policy.reasons import Reason, reason

# The numbers the student approved. If any of them differs at execution, refuse.
_APPROVED_FIELDS = {
    "payment": ("amount_minor", "currency", "payee_id", "payee_account_ref"),
    "conversion": ("amount_minor", "fee_minor", "amount_received_minor", "offered_rate", "provider_id"),
    "payee": ("name", "account_ref", "bank_name"),
}


@dataclass(frozen=True)
class Outcome:
    kind: str  # executed | refused | needs_otp | needs_cooling_off
    posting_id: int | None = None


def reasons_as_json(reasons: list[Reason]) -> list[dict[str, Any]]:
    return [
        {"code": item.code, "severity": item.severity, "title": item.title, "text": item.text}
        for item in reasons
    ]


def refuse(session: Session, action: PendingAction, verdict: Verdict, stage: str, now: datetime) -> None:
    """Mark an action refused and log the verdict and the refusal."""
    codes = [item.code for item in verdict.reasons]
    action.status = "refused"
    action.tier = "REFUSED"
    action.reasons = reasons_as_json(verdict.reasons)
    action.expires_at = None
    audit.append(
        session,
        "policy.verdict",
        "policy",
        {"action_id": action.id, "tool": action.tool, "tier": "REFUSED", "reasons": codes, "stage": stage},
        now=now,
    )
    audit.append(
        session,
        "action.refused",
        "policy",
        {"action_id": action.id, "tool": action.tool, "reasons": codes, "stage": stage},
        now=now,
    )


def _cost_changed(approved: dict[str, Any] | None, current: dict[str, Any] | None) -> bool:
    approved, current = approved or {}, current or {}
    fields = _APPROVED_FIELDS.get(str(current.get("kind")), ())
    return any(approved.get(name) != current.get(name) for name in fields)


def execute(
    session: Session, user: User, action: PendingAction, satisfied: set[str], today: date, now: datetime
) -> Outcome:
    """
    Run an approved action, if the policy still allows it right now.

    `satisfied` lists the steps the student has completed (confirm, otp, cooling_off).
    """
    verdict = evaluate(user, action.tool, action.args, Context(session, today, now, action_id=action.id))
    if verdict.tier == "REFUSED":
        refuse(session, action, verdict, "execution", now)
        return Outcome("refused")

    missing = [step for step in verdict.requires if step not in satisfied]
    if missing:
        # The situation now needs more than was approved: raise the tier, never lower it.
        if TIER_RANK[verdict.tier] > TIER_RANK[action.tier]:
            action.tier = verdict.tier
            action.reasons = reasons_as_json(verdict.reasons)
            audit.append(
                session,
                "policy.verdict",
                "policy",
                {
                    "action_id": action.id,
                    "tool": action.tool,
                    "tier": verdict.tier,
                    "reasons": [item.code for item in verdict.reasons],
                    "stage": "recheck",
                },
                now=now,
            )
        return Outcome("needs_otp" if "otp" in missing else "needs_cooling_off")

    if _cost_changed(action.cost_breakdown, verdict.cost_breakdown):
        refuse(session, action, Verdict(tier="REFUSED", reasons=[reason("QUOTE_CHANGED")]), "execution", now)
        return Outcome("refused")

    audit.append(
        session,
        "policy.verdict",
        "policy",
        {
            "action_id": action.id,
            "tool": action.tool,
            "tier": verdict.tier,
            "reasons": [item.code for item in verdict.reasons],
            "stage": "execution",
        },
        now=now,
    )
    breakdown = verdict.cost_breakdown or {}
    posting_id: int | None = None
    if action.tool == "pay_bill":
        posting_id, receipt = _pay_bill(session, user, action, today, now)
    elif action.tool == "convert_currency":
        posting_id, receipt = _convert_currency(session, user, action, breakdown, today, now)
        # The approved quote lasts ten minutes. After that the fresh quote above is the one used;
        # it was already checked to give the same amounts the student approved.
        approved_until = (action.cost_breakdown or {}).get("expires_at")
        receipt["requoted"] = bool(approved_until) and now > datetime.fromisoformat(approved_until)
    elif action.tool == "add_payee":
        receipt = _add_payee(session, user, breakdown, now)
    else:
        raise RuntimeError(f"No executor for {action.tool}.")

    action.status = "executed"
    action.executed_posting_id = posting_id
    action.expires_at = None
    audit.append(
        session,
        "action.executed",
        "system",
        {"action_id": action.id, "tool": action.tool, "posting_id": posting_id, "receipt": receipt},
        now=now,
    )
    return Outcome("executed", posting_id)


def _pay_bill(
    session: Session, user: User, action: PendingAction, today: date, now: datetime
) -> tuple[int, dict[str, Any]]:
    # The amount and the payee come from the bill record, never from the arguments.
    bill = session.get_one(Bill, action.args["bill_id"])
    payee = bill.payee
    posting = post(
        session,
        kind="payment",
        legs=payment_legs(session, user.id, bill.currency, bill.amount_minor),
        business_date=today,
        created_at=now,
        category="bill_payment",
        counterparty=payee.name,
        description=f"Bill #{bill.id}",
        action_id=action.id,
    )
    bill.status = "paid"
    if payee.first_paid_at is None:
        payee.first_paid_at = today
    return posting.id, {
        "kind": "payment",
        "bill_id": bill.id,
        "payee_name": payee.name,
        "payee_account_ref": payee.account_ref,
        "amount_minor": bill.amount_minor,
        "currency": bill.currency,
        "business_date": today,
    }


def _convert_currency(
    session: Session, user: User, action: PendingAction, quote: dict[str, Any], today: date, now: datetime
) -> tuple[int, dict[str, Any]]:
    posting = post(
        session,
        kind="conversion",
        legs=conversion_legs(
            session,
            user.id,
            sell_currency=quote["from_currency"],
            sell_minor=quote["amount_minor"],
            fee_minor=quote["fee_minor"],
            buy_currency=quote["to_currency"],
            buy_minor=quote["amount_received_minor"],
        ),
        business_date=today,
        created_at=now,
        category="conversion",
        counterparty=quote["provider_name"],
        description=f"Convert {quote['from_currency']} to {quote['to_currency']}",
        action_id=action.id,
    )
    return posting.id, {
        "kind": "conversion",
        "provider_name": quote["provider_name"],
        "from_currency": quote["from_currency"],
        "to_currency": quote["to_currency"],
        "amount_minor": quote["amount_minor"],
        "fee_minor": quote["fee_minor"],
        "markup_cost_minor": quote["markup_cost_minor"],
        "amount_received_minor": quote["amount_received_minor"],
        "mid_rate": quote["mid_rate"],
        "offered_rate": quote["offered_rate"],
        "business_date": today,
    }


def _add_payee(session: Session, user: User, details: dict[str, Any], now: datetime) -> dict[str, Any]:
    payee = Payee(
        user_id=user.id,
        name=details["name"],
        account_ref=details["account_ref"],
        bank_name=details["bank_name"],
        verified_source="manual",
        created_at=now,
    )
    session.add(payee)
    session.flush()
    return {"kind": "payee", "payee_id": payee.id, "name": payee.name, "account_ref": payee.account_ref}
