"""Ahmad's 90 days of transaction history, built from fixed rules (no randomness)."""

from dataclasses import dataclass
from datetime import date, timedelta

from app.money import to_minor

HISTORY_DAYS = 90
TUITION_DAYS_AGO = 60  # last semester's tuition
RECENT_DAYS = 30  # the window the Home page compares with the 30 days before it

UNIVERSITY_NAME = "Shenzhen Polytechnic International University"
# The landlord and account on the demo rent invoice (demo-docs/invoice_injection_en.pdf).
LANDLORD_NAME = "Lingnan Student Housing"
LANDLORD_ACCOUNT = "3300 1188 2026 0042"
PHONE_COMPANY_NAME = "PearlTel Mobile"

# Everyday spending in CNY. Each list is used in order and repeats. Food costs more
# in the most recent 30 days, which is what the spending insight picks up.
GROCERIES_EARLIER = ["96.40", "128.75", "88.20", "142.60", "104.30", "118.90"]
GROCERIES_RECENT = ["112.40", "145.60", "99.80", "163.50", "118.70", "134.20"]
EATING_OUT_EARLIER = [
    "28.00", "46.50", "35.80", "62.00", "24.50", "52.30", "38.00", "71.20", "31.60", "44.90",
]  # fmt: skip
EATING_OUT_RECENT = [
    "35.00", "57.60", "44.50", "76.80", "30.40", "64.90", "47.00", "88.50", "39.20", "55.60",
]  # fmt: skip
GROCERY_SHOPS = ["Campus Mini Mart", "Nanshan Fresh Market"]
RESTAURANTS = ["Campus Canteen", "Old Chen Noodle House", "Halal Lanzhou Kitchen", "Riverside Hotpot"]


@dataclass(frozen=True)
class HistoryItem:
    business_date: date
    kind: str  # income | expense | payment
    category: str
    currency: str
    amount_minor: int  # always positive; `kind` gives the direction
    counterparty: str
    description: str


def _item(
    day: date, kind: str, category: str, currency: str, amount: str, counterparty: str, description: str
) -> HistoryItem:
    return HistoryItem(day, kind, category, currency, to_minor(amount, currency), counterparty, description)


def _monthly(day: date) -> list[HistoryItem]:
    """Items tied to a day of the month: stipend, rent, phone bill, subscriptions."""
    month = day.strftime("%B %Y")
    if day.day == 1:
        return [
            _item(day, "income", "stipend", "MYR", "2500.00", "Monthly stipend", f"Stipend for {month}"),
            _item(day, "payment", "rent", "CNY", "2800.00", LANDLORD_NAME, f"Rent for {month}"),
        ]
    if day.day == 5:
        return [_item(day, "expense", "subscriptions", "USD", "5.99", "Music streaming", "Monthly subscription")]
    if day.day == 20:
        return [_item(day, "expense", "subscriptions", "USD", "2.99", "Cloud storage", "Monthly subscription")]
    if day.day == 28:
        return [_item(day, "payment", "phone", "CNY", "98.00", PHONE_COMPANY_NAME, f"Phone bill for {month}")]
    return []


def _everyday(day: date, days_ago: int) -> list[HistoryItem]:
    """Groceries every 5 days, eating out every 3, a metro top-up every 6."""
    recent = days_ago < RECENT_DAYS
    items: list[HistoryItem] = []
    if days_ago % 5 == 2:
        amounts = GROCERIES_RECENT if recent else GROCERIES_EARLIER
        turn = days_ago // 5
        shop = GROCERY_SHOPS[turn % len(GROCERY_SHOPS)]
        items.append(_item(day, "expense", "groceries", "CNY", amounts[turn % len(amounts)], shop, "Groceries"))
    if days_ago % 3 == 0:
        amounts = EATING_OUT_RECENT if recent else EATING_OUT_EARLIER
        turn = days_ago // 3
        place = RESTAURANTS[turn % len(RESTAURANTS)]
        items.append(_item(day, "expense", "eating_out", "CNY", amounts[turn % len(amounts)], place, "Meal"))
    if days_ago % 6 == 4:
        items.append(_item(day, "expense", "transport", "CNY", "50.00", "Metro card", "Metro card top-up"))
    return items


def build_history(today: date) -> list[HistoryItem]:
    """Every history item for the 90 days ending at `today`, oldest first."""
    items: list[HistoryItem] = []
    for days_ago in range(HISTORY_DAYS - 1, -1, -1):
        day = today - timedelta(days=days_ago)
        items += _monthly(day)
        if days_ago == TUITION_DAYS_AGO:
            items.append(
                _item(day, "payment", "tuition", "CNY", "11500.00", UNIVERSITY_NAME, "Tuition, last semester")
            )
        items += _everyday(day, days_ago)
    return items
