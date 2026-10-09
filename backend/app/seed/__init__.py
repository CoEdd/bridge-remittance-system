"""Deterministic demo data. reset() rebuilds the whole database from scratch."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.clock import demo_today, now_utc
from app.config import get_settings
from app.db import Base, get_engine
from app.fx import freeze_rates
from app.ledger import SYSTEM_ROLES, income_legs, payment_legs, post, user_account
from app.models import Account, Bill, Institution, Payee, Provider, User
from app.money import CURRENCIES, to_minor
from app.seed.history import (
    HISTORY_DAYS,
    LANDLORD_NAME,
    PHONE_COMPANY_NAME,
    TUITION_DAYS_AGO,
    UNIVERSITY_NAME,
    HistoryItem,
    build_history,
)

DEMO_USER_ID = 1
UNIVERSITY_PAYEE_ID = 1
LANDLORD_PAYEE_ID = 2
PHONE_PAYEE_ID = 3

# Where the history must end up, exactly.
TARGET_BALANCES = {
    "MYR": to_minor("9850.00", "MYR"),
    "CNY": to_minor("3420.00", "CNY"),
    "USD": to_minor("180.00", "USD"),
}

# The university's official fee account. The bank is fictional, like the university.
UNIVERSITY_ACCOUNT = "4100 2026 0000 8815"
BANK_NAME = "Shenzhen Bay Commercial Bank (深圳湾商业银行)"


class SeedError(RuntimeError):
    pass


def _seed_time(day: date, order: int) -> datetime:
    """A fixed timestamp for seeded rows, so two resets produce identical data."""
    return datetime(day.year, day.month, day.day, 4, 0, tzinfo=timezone.utc) + timedelta(seconds=order)


def _opening_balances(history: list[HistoryItem]) -> dict[str, int]:
    """Opening balance per currency: the target minus everything the history adds."""
    net = dict.fromkeys(CURRENCIES, 0)
    for item in history:
        net[item.currency] += item.amount_minor if item.kind == "income" else -item.amount_minor
    return {currency: TARGET_BALANCES[currency] - net[currency] for currency in CURRENCIES}


def _add_reference_data(session: Session, today: date) -> None:
    start = today - timedelta(days=HISTORY_DAYS - 1)
    tuition_day = today - timedelta(days=TUITION_DAYS_AGO)

    session.add(
        User(
            id=DEMO_USER_ID,
            name="Ahmad Faris",
            preferred_language="ms",
            home_currency="MYR",
            per_txn_limit_minor=to_minor("5000.00", "MYR"),
            daily_limit_minor=to_minor("10000.00", "MYR"),
            new_payee_limit_minor=to_minor("3000.00", "MYR"),
        )
    )
    session.flush()

    # Ahmad's wallets get ids 1 to 3, then the system accounts in a fixed order.
    wallets = [
        Account(user_id=DEMO_USER_ID, currency=currency, kind="user", name=f"{currency} wallet")
        for currency in CURRENCIES
    ]
    system = [
        Account(currency=currency, kind="system", name=f"{role}_{currency}")
        for role in SYSTEM_ROLES
        for currency in CURRENCIES
    ]
    for account_id, account in enumerate(wallets + system, start=1):
        account.id = account_id
        session.add(account)

    session.add(
        Institution(
            id=1,
            name=UNIVERSITY_NAME,
            name_local="深圳国际理工大学",
            country="CN",
            official_account_ref=UNIVERSITY_ACCOUNT,
            official_bank_name=BANK_NAME,
        )
    )
    session.flush()
    session.add_all(
        [
            Payee(
                id=UNIVERSITY_PAYEE_ID,
                user_id=DEMO_USER_ID,
                name=UNIVERSITY_NAME,
                account_ref=UNIVERSITY_ACCOUNT,
                bank_name=BANK_NAME,
                institution_id=1,
                verified_source="institution_registry",
                created_at=_seed_time(tuition_day, 0),
                first_paid_at=tuition_day,
            ),
            Payee(
                id=LANDLORD_PAYEE_ID,
                user_id=DEMO_USER_ID,
                name=LANDLORD_NAME,
                account_ref="6230 5500 0031 7742",
                bank_name=BANK_NAME,
                verified_source="past_payment",
                created_at=_seed_time(start, 0),
                first_paid_at=_first_payment_day(start, today, 1),
            ),
            Payee(
                id=PHONE_PAYEE_ID,
                user_id=DEMO_USER_ID,
                name=PHONE_COMPANY_NAME,
                account_ref="4100 5510 0002 3306",
                bank_name=BANK_NAME,
                verified_source="past_payment",
                created_at=_seed_time(start, 0),
                first_paid_at=_first_payment_day(start, today, 28),
            ),
            # The one transfer service. Bridge does not compare services; in production
            # the quote would come from the bank or remittance service running Bridge.
            Provider(
                id=1,
                name="RemitFast (simulated)",
                fee_fixed_minor=to_minor("8.00", "MYR"),
                fee_currency="MYR",
                fee_pct="0",
                markup_pct="1.2",
                delivery_hours=4,
                simulated=True,
            ),
        ]
    )
    session.flush()


def _first_payment_day(start: date, today: date, day_of_month: int) -> date | None:
    """The first date in the history window that falls on `day_of_month`."""
    for offset in range((today - start).days + 1):
        day = start + timedelta(days=offset)
        if day.day == day_of_month:
            return day
    return None


def _add_history(session: Session, today: date) -> None:
    history = build_history(today)
    start = today - timedelta(days=HISTORY_DAYS - 1)

    for order, (currency, amount_minor) in enumerate(_opening_balances(history).items()):
        if amount_minor <= 0:
            raise SeedError(f"The history needs a positive opening balance in {currency}.")
        post(
            session,
            kind="seed",
            legs=income_legs(session, DEMO_USER_ID, currency, amount_minor),
            business_date=start,
            created_at=_seed_time(start, order),
            category="opening_balance",
            description="Opening balance",
        )

    for order, item in enumerate(history, start=len(CURRENCIES)):
        build_legs = income_legs if item.kind == "income" else payment_legs
        post(
            session,
            kind=item.kind,
            legs=build_legs(session, DEMO_USER_ID, item.currency, item.amount_minor),
            business_date=item.business_date,
            created_at=_seed_time(item.business_date, order),
            category=item.category,
            counterparty=item.counterparty,
            description=item.description,
        )

    for currency, target in TARGET_BALANCES.items():
        balance = user_account(session, DEMO_USER_ID, currency).balance_minor
        if balance != target:
            raise SeedError(f"{currency} ended at {balance} minor units, expected {target}.")


def _add_bills(session: Session) -> None:
    session.add_all(
        [
            Bill(
                id=1,
                user_id=DEMO_USER_ID,
                payee_id=LANDLORD_PAYEE_ID,
                amount_minor=to_minor("2800.00", "CNY"),
                currency="CNY",
                due_date=date(2026, 11, 1),
                status="open",
            ),
            Bill(
                id=2,
                user_id=DEMO_USER_ID,
                payee_id=PHONE_PAYEE_ID,
                amount_minor=to_minor("98.00", "CNY"),
                currency="CNY",
                due_date=date(2026, 10, 28),
                status="open",
            ),
        ]
    )
    session.flush()


def _write_audit_genesis(session: Session) -> None:
    """
    HOOK FOR STEP 4. The audit module does not exist yet, so this does nothing.
    Step 4 should write the audit log's genesis entry here, inside reset()'s transaction.
    """


def reset() -> str:
    """
    Drop and recreate every table, seed the demo data and freeze the FX rates.
    Returns the FX source ("frankfurter" or "offline_snapshot").
    """
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    today = demo_today()
    with Session(engine) as session:
        _add_reference_data(session, today)
        _add_history(session, today)
        _add_bills(session)
        source = freeze_rates(session, offline=get_settings().fx_offline, now=now_utc())
        _write_audit_genesis(session)
        session.commit()
    return source


def ensure_seeded() -> None:
    """Create the tables and seed them if the database is empty (first start)."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seeded = session.scalar(select(User.id).limit(1)) is not None
    if not seeded:
        reset()
