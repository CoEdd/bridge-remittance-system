"""
The funding planner: how to pay a bill across the student's wallets and upcoming bills.

It only plans. Each step carries the tier the policy engine would give it, found by a
dry run that writes nothing. Proposing and executing happen elsewhere.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.documents import bill_is_flagged
from app.fx import FxError, get_transfer_quote, quote_to_receive
from app.ledger import user_account
from app.models import Bill, User
from app.money import format_amount
from app.policy import Context, evaluate

BUFFER_CURRENCY = "CNY"


@dataclass
class PlannedStep:
    tool: str
    args: dict[str, Any]
    predicted_tier: str  # from a policy dry run
    requires: list[str]
    reasons: list[str]  # reason codes
    cost_breakdown: dict[str, Any] | None
    summary: str


@dataclass
class FundingPlan:
    bill_id: int
    # ready: enough in the wallet | needs_conversion | insufficient_funds | not_payable
    status: str
    currency: str = ""
    bill_amount_minor: int = 0
    counted_bills: list[dict[str, Any]] = field(default_factory=list)
    buffer_minor: int = 0
    required_minor: int = 0
    balance_minor: int = 0
    shortfall_minor: int = 0
    source_currency: str | None = None
    source_balance_minor: int | None = None
    # When the source wallet cannot cover the shortfall: the most that can be converted.
    affordable: dict[str, int] | None = None
    steps: list[PlannedStep] = field(default_factory=list)
    explanation: str = ""


def _dry_run(user: User, tool: str, args: dict[str, Any], ctx: Context, summary: str) -> PlannedStep:
    verdict = evaluate(user, tool, args, ctx)
    return PlannedStep(
        tool=tool,
        args=args,
        predicted_tier=verdict.tier,
        requires=verdict.requires,
        reasons=[item.code for item in verdict.reasons],
        cost_breakdown=verdict.cost_breakdown,
        summary=summary,
    )


def plan_funding(session: Session, user: User, bill_id: int, today: date, now: datetime) -> FundingPlan:
    """
    Plan the payment of one bill.

    Needed in the bill's currency: this bill, plus every other open bill in that currency
    due on or before it that comes from a trusted, unflagged source, plus a buffer
    (CNY 500.00 by default). A shortfall is covered by one conversion from the home
    currency. The amount is never split to stay under a limit.
    """
    bill = session.get(Bill, bill_id)
    if bill is None or bill.user_id != user.id or bill.status != "open":
        return FundingPlan(bill_id=bill_id, status="not_payable", explanation="This bill is not open.")

    currency = bill.currency
    wallet = user_account(session, user.id, currency)
    others = [
        other
        for other in session.scalars(
            select(Bill).where(
                Bill.user_id == user.id, Bill.status == "open", Bill.currency == currency, Bill.id != bill.id
            )
        )
        if other.due_date and bill.due_date and other.due_date <= bill.due_date and not bill_is_flagged(other)
    ]
    counted = sorted([bill, *others], key=lambda item: (item.due_date or date.max, item.id))
    buffer_minor = get_settings().funding_buffer_minor if currency == BUFFER_CURRENCY else 0
    required = sum(item.amount_minor for item in counted) + buffer_minor
    shortfall = max(0, required - wallet.balance_minor)

    plan = FundingPlan(
        bill_id=bill.id,
        status="ready",
        currency=currency,
        bill_amount_minor=bill.amount_minor,
        counted_bills=[
            {
                "bill_id": item.id,
                "payee_name": item.payee.name,
                "amount_minor": item.amount_minor,
                "due_date": item.due_date.isoformat() if item.due_date else None,
            }
            for item in counted
        ],
        buffer_minor=buffer_minor,
        required_minor=required,
        balance_minor=wallet.balance_minor,
        shortfall_minor=shortfall,
    )
    counted_text = ", ".join(
        f"{item.payee.name} {format_amount(item.amount_minor, currency)}" for item in counted
    )
    needed_text = (
        f"Counted: {counted_text}"
        + (f", buffer {format_amount(buffer_minor, currency)}" if buffer_minor else "")
        + f". Needed {format_amount(required, currency)}, balance {format_amount(wallet.balance_minor, currency)}."
    )
    pay_args = {"bill_id": bill.id, "from_account_id": wallet.id}
    pay_summary = f"Pay {format_amount(bill.amount_minor, currency)} to {bill.payee.name}"

    if shortfall == 0:
        plan.steps = [_dry_run(user, "pay_bill", pay_args, Context(session, today, now), pay_summary)]
        plan.explanation = f"{needed_text} No conversion is needed."
        return plan

    source = user.home_currency
    plan.source_currency = source
    try:
        quote = quote_to_receive(session, shortfall, source, currency, now)
    except FxError:
        plan.status = "insufficient_funds"
        plan.explanation = f"{needed_text} Short by {format_amount(shortfall, currency)}, and {source} cannot be converted to {currency} here."
        return plan

    source_wallet = user_account(session, user.id, source)
    plan.source_balance_minor = source_wallet.balance_minor
    if quote.total_debit_minor > source_wallet.balance_minor:
        plan.status = "insufficient_funds"
        most = source_wallet.balance_minor - quote.fee_minor
        if most > 0:
            affordable = get_transfer_quote(session, most, source, currency, now)
            plan.affordable = {
                "amount_minor": affordable.amount_minor,
                "fee_minor": affordable.fee_minor,
                "receives_minor": affordable.amount_received_minor,
            }
        plan.explanation = (
            f"{needed_text} Short by {format_amount(shortfall, currency)}. Covering it needs "
            f"{format_amount(quote.total_debit_minor, source)}, more than the {source} wallet holds."
        )
        return plan

    convert_args = {
        "from_currency": source,
        "to_currency": currency,
        "amount_minor": quote.amount_minor,
        "provider_id": quote.provider_id,
    }
    plan.status = "needs_conversion"
    plan.steps = [
        _dry_run(
            user,
            "convert_currency",
            convert_args,
            Context(session, today, now),
            f"Convert {format_amount(quote.amount_minor, source)} to {currency}",
        ),
        # The payment is checked as if the conversion above had already arrived.
        _dry_run(
            user,
            "pay_bill",
            pay_args,
            Context(session, today, now, planned_proceeds={currency: quote.amount_received_minor}),
            pay_summary,
        ),
    ]
    plan.explanation = (
        f"{needed_text} Short by {format_amount(shortfall, currency)}. Convert "
        f"{format_amount(quote.amount_minor, source)} (fee {format_amount(quote.fee_minor, source)}) to receive "
        f"{format_amount(quote.amount_received_minor, currency)}, then pay the bill."
    )
    return plan
