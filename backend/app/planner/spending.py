"""Spending analysis: category totals, change against the previous period, a forecast."""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.documents import bill_is_flagged
from app.fx import get_mid_rate
from app.ledger import user_account
from app.models import Account, Bill, Entry, Posting, User
from app.money import convert

PERIOD_DAYS = 30
FORECAST_CURRENCY = "CNY"
# Changes smaller than this are treated as "about the same".
MIN_CHANGE_PCT = 5

SPENDING_KINDS = ("expense", "payment", "fee")
EVERYDAY_KIND = "expense"

CATEGORY_LABELS = {
    "stipend": "Stipend",
    "rent": "Rent",
    "tuition": "Tuition",
    "phone": "Phone",
    "groceries": "Groceries",
    "eating_out": "Eating out",
    "transport": "Transport",
    "subscriptions": "Subscriptions",
    "opening_balance": "Opening balance",
    "conversion": "Currency conversion",
    "bill_payment": "Bill payment",
    "transfer_in": "Money received",
    "fees": "Fees",
}


def category_label(category: str | None) -> str:
    if category is None:
        return "Other"
    return CATEGORY_LABELS.get(category, category.replace("_", " ").capitalize())


@dataclass(frozen=True)
class CategorySpend:
    category: str
    label: str
    currency: str
    total_minor: int
    previous_total_minor: int
    change_pct: int | None  # None when there was nothing to compare with
    home_equivalent_minor: int
    home_change_minor: int


@dataclass(frozen=True)
class Forecast:
    currency: str
    as_of: date
    month_end: date
    balance_minor: int
    bills_due_minor: int
    projected_spending_minor: int
    forecast_minor: int


@dataclass(frozen=True)
class SpendingInsights:
    home_currency: str
    period_days: int
    period_start: date
    period_end: date
    categories: list[CategorySpend]
    forecast: Forecast
    insight: str


def _spend_by_category(
    session: Session, user_id: int, start: date, end: date, kinds: tuple[str, ...]
) -> dict[tuple[str, str], int]:
    """Money that left the user's accounts between two dates, by (category, currency)."""
    rows = session.execute(
        select(Posting.category, Entry.currency, func.sum(-Entry.amount_minor))
        .select_from(Entry)
        .join(Posting, Entry.posting_id == Posting.id)
        .join(Account, Entry.account_id == Account.id)
        .where(
            Account.user_id == user_id,
            Posting.kind.in_(kinds),
            Entry.amount_minor < 0,
            Posting.business_date.between(start, end),
        )
        .group_by(Posting.category, Entry.currency)
    )
    return {(category or "other", currency): int(total) for category, currency, total in rows}


def _change_pct(current: int, previous: int) -> int | None:
    if previous == 0:
        return None
    change = Decimal(current - previous) * 100 / Decimal(previous)
    return int(change.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _insight_sentence(categories: list[CategorySpend]) -> str:
    """One sentence about the category whose spending moved the most, in home-currency terms."""
    if not categories:
        return f"There was no spending in the last {PERIOD_DAYS} days."
    movers = [
        item
        for item in categories
        if item.change_pct is not None and abs(item.change_pct) >= MIN_CHANGE_PCT
    ]
    if not movers:
        return (
            f"Spending in every category is within {MIN_CHANGE_PCT}% "
            f"of the previous {PERIOD_DAYS} days."
        )
    top = max(movers, key=lambda item: abs(item.home_change_minor))
    assert top.change_pct is not None
    direction = "up" if top.change_pct > 0 else "down"
    return (
        f"{top.label} is {direction} {abs(top.change_pct)}% "
        f"compared with the previous {PERIOD_DAYS} days."
    )


def _forecast(session: Session, user: User, today: date) -> Forecast:
    """
    Expected balance at month end: today's balance, minus open bills due by then,
    minus everyday spending continuing at the last 30 days' daily average.
    """
    month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    start = today - timedelta(days=PERIOD_DAYS - 1)
    everyday = sum(
        total
        for (_, currency), total in _spend_by_category(
            session, user.id, start, today, (EVERYDAY_KIND,)
        ).items()
        if currency == FORECAST_CURRENCY
    )
    days_left = (month_end - today).days
    projected = -(-everyday * days_left // PERIOD_DAYS)  # rounded up
    open_bills = session.scalars(
        select(Bill).where(
            Bill.user_id == user.id,
            Bill.status == "open",
            Bill.currency == FORECAST_CURRENCY,
            Bill.due_date.between(today, month_end),
        )
    )
    # A bill from an untrusted or risky document is not something to plan for.
    bills_due = sum(bill.amount_minor for bill in open_bills if not bill_is_flagged(bill))
    balance = user_account(session, user.id, FORECAST_CURRENCY).balance_minor
    return Forecast(
        currency=FORECAST_CURRENCY,
        as_of=today,
        month_end=month_end,
        balance_minor=balance,
        bills_due_minor=bills_due,
        projected_spending_minor=projected,
        forecast_minor=balance - bills_due - projected,
    )


def analyse_spending(session: Session, user: User, today: date) -> SpendingInsights:
    start = today - timedelta(days=PERIOD_DAYS - 1)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=PERIOD_DAYS - 1)

    current = _spend_by_category(session, user.id, start, today, SPENDING_KINDS)
    previous = _spend_by_category(session, user.id, previous_start, previous_end, SPENDING_KINDS)

    categories = []
    for (category, currency), total in current.items():
        before = previous.get((category, currency), 0)
        to_home = get_mid_rate(session, currency, user.home_currency)
        categories.append(
            CategorySpend(
                category=category,
                label=category_label(category),
                currency=currency,
                total_minor=total,
                previous_total_minor=before,
                change_pct=_change_pct(total, before),
                home_equivalent_minor=convert(total, to_home),
                home_change_minor=convert(total, to_home) - convert(before, to_home),
            )
        )
    categories.sort(key=lambda item: (-item.home_equivalent_minor, item.category))

    return SpendingInsights(
        home_currency=user.home_currency,
        period_days=PERIOD_DAYS,
        period_start=start,
        period_end=today,
        categories=categories,
        forecast=_forecast(session, user, today),
        insight=_insight_sentence(categories),
    )
