"""
The policy engine. Plain Python: it never calls an LLM and never reads chat text.

evaluate() looks only at the tool name, its arguments and facts in the database,
and answers with a tier, the reasons, and what the student must do before the
action may run.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_UP, Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.fx import SUPPORTED_CONVERSIONS, get_mid_rate, transfer_quote
from app.ledger import user_account
from app.models import Account, Bill, Document, Entry, PendingAction, Posting, Provider, User
from app.money import Currency
from app.policy.reasons import DOCUMENT_RISK_SIGNALS, Reason, reason

Tier = Literal["T0", "T1", "T2", "T3", "REFUSED"]
TIER_RANK: dict[str, int] = {"T0": 0, "T1": 1, "T2": 2, "T3": 3, "REFUSED": 4}

BASE_TIERS: dict[str, Tier] = {
    # T0 Read: automatic.
    "get_balances": "T0",
    "get_transactions": "T0",
    "read_document": "T0",
    "get_fx_rate": "T0",
    "get_transfer_quote": "T0",
    "verify_payee": "T0",
    "explain_decision": "T0",
    "respond_to_user": "T0",
    # T1 Suggest: automatic, only proposes.
    "analyse_spending": "T1",
    "plan_funding": "T1",
    # T2 Confirm: the student confirms the exact amount, currency and payee.
    "convert_currency": "T2",
    "pay_bill": "T2",
    # T3 Step-up: confirm plus a one-time code.
    "add_payee": "T3",
}

# Actions in these states still count towards the per-payment limit.
LIVE_STATUSES = ("awaiting_confirm", "awaiting_otp", "cooling_off", "executed")
MULE_WINDOW = timedelta(hours=72)


@dataclass(frozen=True)
class Context:
    """Facts the engine needs besides the arguments."""

    session: Session
    today: date  # demo clock: business dates
    now: datetime  # real UTC
    action_id: int | None = None  # set when re-checking an existing pending action
    # Set when an action is proposed as part of a plan. Money that the plan's own waiting
    # conversions will bring in then counts as funds for its payment. At execution time
    # this is never set, so only money really in the wallet counts.
    plan_id: str | None = None
    # Planner dry runs only: funds a not-yet-proposed conversion would bring, by currency.
    planned_proceeds: dict[str, int] = field(default_factory=dict)


@dataclass
class Verdict:
    tier: Tier
    reasons: list[Reason] = field(default_factory=list)
    cost_breakdown: dict[str, Any] | None = None

    @property
    def requires(self) -> list[str]:
        """What the student must do first: a subset of confirm, otp, cooling_off."""
        return requires_for(self.tier, [item.code for item in self.reasons])

    def raise_to(self, tier: Tier, because: Reason | None = None) -> None:
        """Context can raise a tier, never lower it."""
        if TIER_RANK[tier] > TIER_RANK[self.tier]:
            self.tier = tier
        if because and because not in self.reasons:
            self.reasons.append(because)


def requires_for(tier: str, reason_codes: list[str]) -> list[str]:
    """The steps needed for a tier and its reasons. Stored actions use this too."""
    if tier not in ("T2", "T3"):
        return []
    extra = {step for code in reason_codes for step in reason(code).requires}
    if tier == "T3":
        extra.add("otp")
    return ["confirm", *[step for step in ("otp", "cooling_off") if step in extra]]


def _refused(*codes: str, cost_breakdown: dict[str, Any] | None = None) -> Verdict:
    return Verdict(tier="REFUSED", reasons=[reason(code) for code in codes], cost_breakdown=cost_breakdown)


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PayBillArgs(_Args):
    bill_id: StrictInt
    from_account_id: StrictInt
    # Optional values the LLM may supply. They are only ever compared with the bill.
    amount_minor: StrictInt | None = None
    currency: str | None = None
    payee_id: StrictInt | None = None


class ConvertCurrencyArgs(_Args):
    from_currency: Currency
    to_currency: Currency
    amount_minor: StrictInt = Field(gt=0)
    provider_id: StrictInt


class AddPayeeArgs(_Args):
    name: str = Field(min_length=1, max_length=120)
    account_ref: str = Field(min_length=1, max_length=64)
    bank_name: str = Field(min_length=1, max_length=120)


def home_equivalent(session: Session, user: User, amount_minor: int, currency: str) -> int:
    """MYR-equivalent at the frozen mid-market rate, rounded up so limits are never under-counted."""
    rate = get_mid_rate(session, currency, user.home_currency)
    return int((Decimal(amount_minor) * rate).to_integral_value(rounding=ROUND_UP))


def evaluate(user: User, tool_name: str, args: dict[str, Any], ctx: Context) -> Verdict:
    if tool_name not in BASE_TIERS:
        return _refused("UNKNOWN_TOOL")
    if tool_name == "pay_bill":
        return _pay_bill(user, args, ctx)
    if tool_name == "convert_currency":
        return _convert_currency(user, args, ctx)
    if tool_name == "add_payee":
        return _add_payee(args)
    return Verdict(tier=BASE_TIERS[tool_name])


# ---------------------------------------------------------------- pay_bill


def _pay_bill(user: User, raw_args: dict[str, Any], ctx: Context) -> Verdict:
    try:
        args = PayBillArgs.model_validate(raw_args)
    except ValidationError:
        return _refused("INVALID_ARGUMENTS")
    session = ctx.session
    bill = session.get(Bill, args.bill_id)
    account = session.get(Account, args.from_account_id)

    # Group 1, integrity. Stop here if anything fails.
    if bill is None or bill.user_id != user.id or bill.status != "open":
        return _refused("BILL_NOT_PAYABLE")
    supplied_differs = (
        args.amount_minor not in (None, bill.amount_minor)
        or args.currency not in (None, bill.currency)
        or args.payee_id not in (None, bill.payee_id)
    )
    wrong_account = account is None or account.user_id != user.id or account.currency != bill.currency
    if supplied_differs or wrong_account:
        return _refused("ARGUMENT_MISMATCH")
    assert account is not None

    # From here on, the amount and the payee are always the bill's, never the LLM's.
    payee = bill.payee
    amount_home = home_equivalent(session, user, bill.amount_minor, bill.currency)
    cost_breakdown = {
        "kind": "payment",
        "bill_id": bill.id,
        "payee_id": payee.id,
        "payee_name": payee.name,
        "payee_account_ref": payee.account_ref,
        "amount_minor": bill.amount_minor,
        "currency": bill.currency,
        "fee_minor": 0,
        "total_minor": bill.amount_minor,
        "home_currency": user.home_currency,
        "home_equivalent_minor": amount_home,
    }

    # Group 2, fraud.
    fraud: list[str] = []
    document = session.get(Document, bill.document_id) if bill.document_id else None
    if document is not None:
        if document.trust_flag == "untrusted":
            fraud.append("UNTRUSTED_DOCUMENT")
        present = _signal_codes(document.risk_signals)
        fraud += [signal for signal in DOCUMENT_RISK_SIGNALS if signal in present]
    if _is_money_mule_pattern(user, bill, ctx):
        fraud.append("MONEY_MULE_PATTERN")
    if fraud:
        return _refused(*fraud, cost_breakdown=cost_breakdown)

    # Group 3, limits and funds.
    limits: list[str] = []
    if _paid_out_today(user, ctx) + amount_home > user.daily_limit_minor:
        limits.append("DAILY_LIMIT")
    if account.balance_minor + _planned_proceeds(user, ctx, bill.currency) < bill.amount_minor:
        limits.append("INSUFFICIENT_FUNDS")
    new_payee = payee.first_paid_at is None
    if new_payee and amount_home > user.new_payee_limit_minor:
        limits.append("NEW_PAYEE_LIMIT")
    if limits:
        return _refused(*limits, cost_breakdown=cost_breakdown)

    # Tiering. Only ever upwards.
    verdict = Verdict(tier=BASE_TIERS["pay_bill"], cost_breakdown=cost_breakdown)
    same_day = _same_day_total(user, ctx, "pay_bill", lambda other: other.get("payee_id") == payee.id)
    if same_day + amount_home > user.per_txn_limit_minor:
        verdict.raise_to("T3", reason("OVER_TXN_LIMIT"))
    if new_payee:
        verdict.raise_to("T3", reason("NEW_PAYEE"))
    return verdict


def _signal_codes(risk_signals: Any) -> set[str]:
    """Risk signals are stored as a list of codes or of objects with a "code"."""
    codes = set()
    for item in risk_signals or []:
        if isinstance(item, str):
            codes.add(item)
        elif isinstance(item, dict) and isinstance(item.get("code"), str):
            codes.add(item["code"])
    return codes


def _is_money_mule_pattern(user: User, bill: Bill, ctx: Context) -> bool:
    """
    Money arrived from someone who never sent money before, in the last 72 hours,
    and this payment sends a similar amount (within 20%) to a payee created afterwards.
    """
    session = ctx.session
    payee = bill.payee
    recent_inbound = session.execute(
        select(Posting, Entry)
        .join(Entry, Entry.posting_id == Posting.id)
        .join(Account, Entry.account_id == Account.id)
        .where(
            Account.user_id == user.id,
            Posting.kind == "income",
            Entry.amount_minor > 0,
            Posting.created_at >= ctx.now - MULE_WINDOW,
            Posting.created_at <= ctx.now,
        )
    ).all()
    for posting, entry in recent_inbound:
        if payee.created_at <= posting.created_at or not _is_first_time_sender(session, user, posting):
            continue
        sent, received = bill.amount_minor, entry.amount_minor
        if entry.currency != bill.currency:  # compare in MYR only when the currencies differ
            sent = home_equivalent(session, user, sent, bill.currency)
            received = home_equivalent(session, user, received, entry.currency)
        if abs(sent - received) * 5 <= received:
            return True
    return False


def _is_first_time_sender(session: Session, user: User, posting: Posting) -> bool:
    if posting.counterparty is None:
        return True
    earlier = session.scalar(
        select(Posting.id)
        .join(Entry, Entry.posting_id == Posting.id)
        .join(Account, Entry.account_id == Account.id)
        .where(
            Account.user_id == user.id,
            Posting.kind == "income",
            Posting.counterparty == posting.counterparty,
            Posting.id != posting.id,
            Posting.created_at < posting.created_at,
        )
        .limit(1)
    )
    return earlier is None


def _planned_proceeds(user: User, ctx: Context, currency: str) -> int:
    """Money the same plan's waiting conversions will add to a wallet (zero outside a plan)."""
    total = ctx.planned_proceeds.get(currency, 0)
    if ctx.plan_id is None:
        return total
    waiting = ctx.session.scalars(
        select(PendingAction).where(
            PendingAction.user_id == user.id,
            PendingAction.plan_id == ctx.plan_id,
            PendingAction.tool == "convert_currency",
            PendingAction.status.in_(("awaiting_confirm", "awaiting_otp", "cooling_off")),
        )
    )
    for action in waiting:
        breakdown = action.cost_breakdown or {}
        if breakdown.get("to_currency") == currency:
            total += int(breakdown.get("amount_received_minor", 0))
    return total


def _paid_out_today(user: User, ctx: Context) -> int:
    """Executed payments to other people on the demo date, MYR-equivalent. Conversions never count."""
    rows = ctx.session.execute(
        select(Entry.amount_minor, Entry.currency)
        .join(Posting, Entry.posting_id == Posting.id)
        .join(Account, Entry.account_id == Account.id)
        .where(
            Account.user_id == user.id,
            Posting.kind == "payment",
            Posting.business_date == ctx.today,
            Entry.amount_minor < 0,
        )
    ).all()
    return sum(home_equivalent(ctx.session, user, -amount, currency) for amount, currency in rows)


def _same_day_total(user: User, ctx: Context, tool: str, same_kind: Any) -> int:
    """
    MYR-equivalent of the student's other pending and executed actions of the same
    kind on the demo date. Splitting an amount into parts therefore never lowers a tier.
    """
    session = ctx.session
    others = session.scalars(
        select(PendingAction).where(
            PendingAction.user_id == user.id,
            PendingAction.tool == tool,
            PendingAction.status.in_(LIVE_STATUSES),
        )
    )
    total = 0
    for other in others:
        breakdown = other.cost_breakdown or {}
        if other.id == ctx.action_id or not same_kind(breakdown):
            continue
        if other.status == "executed":
            posting = session.get(Posting, other.executed_posting_id) if other.executed_posting_id else None
            if posting is None or posting.business_date != ctx.today:
                continue
        total += int(breakdown.get("home_equivalent_minor", 0))
    return total


# ---------------------------------------------------------------- convert_currency


def _convert_currency(user: User, raw_args: dict[str, Any], ctx: Context) -> Verdict:
    try:
        args = ConvertCurrencyArgs.model_validate(raw_args)
    except ValidationError:
        return _refused("INVALID_ARGUMENTS")
    session = ctx.session
    provider = session.get(Provider, args.provider_id)
    if provider is None:
        return _refused("INVALID_ARGUMENTS")
    pair = (args.from_currency, args.to_currency)
    if pair not in SUPPORTED_CONVERSIONS or provider.fee_currency != args.from_currency:
        return _refused("UNSUPPORTED_CONVERSION")

    quote = transfer_quote(session, provider, args.from_currency, args.to_currency, args.amount_minor, ctx.now)
    amount_home = home_equivalent(session, user, args.amount_minor, args.from_currency)
    cost_breakdown = {
        **quote.as_breakdown(),
        "home_currency": user.home_currency,
        "home_equivalent_minor": amount_home,
    }

    wallet = user_account(session, user.id, args.from_currency)
    if wallet.balance_minor < quote.total_debit_minor:
        return _refused("INSUFFICIENT_FUNDS", cost_breakdown=cost_breakdown)

    # Conversions stay inside the student's own wallets, so the daily outbound limit does not apply.
    verdict = Verdict(tier=BASE_TIERS["convert_currency"], cost_breakdown=cost_breakdown)
    same_day = _same_day_total(
        user,
        ctx,
        "convert_currency",
        lambda other: (other.get("from_currency"), other.get("to_currency")) == pair,
    )
    if same_day + amount_home > user.per_txn_limit_minor:
        verdict.raise_to("T3", reason("OVER_TXN_LIMIT"))
    return verdict


# ---------------------------------------------------------------- add_payee


def _add_payee(raw_args: dict[str, Any]) -> Verdict:
    try:
        args = AddPayeeArgs.model_validate(raw_args)
    except ValidationError:
        return _refused("INVALID_ARGUMENTS")
    verdict = Verdict(
        tier=BASE_TIERS["add_payee"],
        cost_breakdown={
            "kind": "payee",
            "name": args.name,
            "account_ref": args.account_ref,
            "bank_name": args.bank_name,
        },
    )
    verdict.raise_to("T3", reason("PAYEE_ADDITION"))
    return verdict
