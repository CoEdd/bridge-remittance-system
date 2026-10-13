"""Deterministic demo data. reset() rebuilds the whole database from scratch."""

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.orm import Session

from app import audit, models  # noqa: F401  (models registers every table on Base.metadata)
from app.clock import demo_today, now_utc
from app.config import get_settings
from app.db import Base, get_engine, write_lock
from app.documents.index import index
from app.fx import freeze_rates
from app.ledger import SYSTEM_ROLES, income_legs, payment_legs, post, user_account
from app.models import Account, AuditLog, Bill, Institution, Payee, Provider, User
from app.money import CURRENCIES, to_minor
from app.seed.history import (
    HISTORY_DAYS,
    LANDLORD_ACCOUNT,
    LANDLORD_NAME,
    PHONE_COMPANY_NAME,
    TUITION_DAYS_AGO,
    UNIVERSITY_NAME,
    HistoryItem,
    build_history,
)

logger = logging.getLogger(__name__)

# Bump whenever a table changes. A database stamped with another number is rebuilt at start-up.
SCHEMA_VERSION = 7

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
            preferred_language="en",
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
                account_ref=LANDLORD_ACCOUNT,
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


def _start_audit_log(session: Session, today: date, fx_source: str) -> None:
    """The first two entries of every chain: the genesis entry, then this reset."""
    audit.append(session, "system.genesis", "system", {"chain": "bridge-audit", "version": 1})
    audit.append(session, "system.reset", "system", {"demo_today": today, "fx_source": fx_source})


def build(engine: Engine, *, offline: bool) -> str:
    """
    Drop and recreate every table in `engine`, seed the demo data, freeze the FX rates and
    start a new audit chain. Returns the FX source ("frankfurter" or "offline_snapshot").
    """
    with write_lock:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text(f"PRAGMA user_version = {SCHEMA_VERSION}"))
        today = demo_today()
        with Session(engine) as session:
            _add_reference_data(session, today)
            _add_history(session, today)
            _add_bills(session)
            source = freeze_rates(session, offline=offline, now=now_utc())
            _start_audit_log(session, today, source)
            session.commit()
    return source


def reset() -> str:
    """Rebuild the live demo database from scratch. Returns the FX source."""
    with write_lock:
        index.reset()
        return build(get_engine(), offline=get_settings().fx_offline)


def _is_current(engine: Engine) -> bool:
    """
    True when the database matches this code: it carries this schema version, every
    table and column exists, the demo user is there, and the audit chain has been started.
    """
    with engine.connect() as connection:
        if connection.execute(text("PRAGMA user_version")).scalar() != SCHEMA_VERSION:
            return False
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            return False
        existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
        if not {column.name for column in table.columns} <= existing_columns:
            return False
    with Session(engine) as session:
        has_user = session.scalar(select(User.id).limit(1)) is not None
        has_audit = session.scalar(select(AuditLog.seq).limit(1)) is not None
    return has_user and has_audit


def ensure_seeded() -> None:
    """
    Called at start-up. A new, empty or out-of-date database (for example a volume left
    by an earlier version of the app) is rebuilt from the seed data. A current one is kept.
    """
    if not _is_current(get_engine()):
        logger.warning("The database is missing or out of date; rebuilding the demo data.")
        reset()
