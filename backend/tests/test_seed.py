from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import Base, get_engine
from app.models import Account, AuditLog, Bill, Entry, Institution, Payee, Posting, Provider, User
from app.planner.spending import analyse_spending
from app.seed import DEMO_USER_ID, ensure_seeded, reset

TODAY = date(2026, 10, 15)

# Wall-clock columns: the only values allowed to differ between two resets. Audit entries
# carry real UTC time by design, and their hashes cover that time.
REAL_TIME_COLUMNS = {
    ("fx_quotes", "fetched_at"),
    ("audit_log", "created_at"),
    ("audit_log", "prev_hash"),
    ("audit_log", "hash"),
}


def wallet_balances(session: Session) -> dict[str, int]:
    rows = session.execute(select(Account.currency, Account.balance_minor).where(Account.user_id == DEMO_USER_ID))
    return {currency: balance for currency, balance in rows}


def dump_database() -> dict[str, list[tuple[Any, ...]]]:
    """Every row of every table, without the wall-clock columns."""
    dump = {}
    with get_engine().connect() as connection:
        for table in Base.metadata.sorted_tables:
            columns = [column for column in table.columns if (table.name, column.name) not in REAL_TIME_COLUMNS]
            rows = connection.execute(select(*columns).order_by(*table.primary_key.columns)).all()
            dump[table.name] = [tuple(row) for row in rows]
    return dump


def test_history_reconciles_to_the_exact_wallet_balances(session: Session) -> None:
    assert wallet_balances(session) == {"MYR": 985_000, "CNY": 342_000, "USD": 18_000}


def test_wallet_balances_equal_the_sum_of_their_entries(session: Session) -> None:
    sums = session.execute(
        select(Account.currency, func.sum(Entry.amount_minor))
        .join(Entry, Entry.account_id == Account.id)
        .where(Account.user_id == DEMO_USER_ID)
        .group_by(Account.currency)
    ).all()

    assert {currency: int(total) for currency, total in sums} == {"MYR": 985_000, "CNY": 342_000, "USD": 18_000}


def test_reset_is_repeatable() -> None:
    reset()
    first = dump_database()
    reset()
    second = dump_database()

    assert first == second
    assert len(first["postings"]) > 60
    assert len(first["accounts"]) == 15
    assert [row[1:3] for row in first["audit_log"]] == [("system.genesis", "system"), ("system.reset", "system")]


def test_reset_restores_changed_data(session: Session) -> None:
    session.get_one(User, DEMO_USER_ID).preferred_language = "ms"
    session.get_one(Bill, 1).status = "paid"
    session.commit()
    session.close()

    reset()

    with Session(get_engine()) as fresh:
        assert fresh.get_one(User, DEMO_USER_ID).preferred_language == "en"
        assert fresh.get_one(Bill, 1).status == "open"


def test_user_and_limits(session: Session) -> None:
    user = session.get_one(User, DEMO_USER_ID)

    assert (user.name, user.preferred_language, user.home_currency) == ("Ahmad Faris", "en", "MYR")
    assert user.per_txn_limit_minor == 500_000
    assert user.daily_limit_minor == 1_000_000
    assert user.new_payee_limit_minor == 300_000


def test_history_covers_90_days_ending_on_the_demo_date(session: Session) -> None:
    first, last = session.execute(select(func.min(Posting.business_date), func.max(Posting.business_date))).one()

    assert last == TODAY
    assert first == TODAY - timedelta(days=89)


def test_monthly_items(session: Session) -> None:
    def rows(category: str) -> list[tuple[date, int, str]]:
        return [
            (posting.business_date, entry.amount_minor, entry.currency)
            for posting in session.scalars(
                select(Posting).where(Posting.category == category).order_by(Posting.business_date)
            )
            for entry in posting.entries
            if entry.account.user_id == DEMO_USER_ID
        ]

    firsts = [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)]
    assert rows("stipend") == [(day, 250_000, "MYR") for day in firsts]
    assert rows("rent") == [(day, -280_000, "CNY") for day in firsts]
    assert rows("phone") == [(date(2026, month, 28), -9_800, "CNY") for month in (7, 8, 9)]
    assert rows("tuition") == [(TODAY - timedelta(days=60), -1_150_000, "CNY")]
    assert len(rows("subscriptions")) == 6
    assert {currency for _, _, currency in rows("subscriptions")} == {"USD"}


def test_food_spending_is_15_to_25_percent_above_the_previous_30_days(session: Session) -> None:
    def food(start: date, end: date) -> int:
        total = session.scalar(
            select(func.sum(-Entry.amount_minor))
            .join(Posting, Entry.posting_id == Posting.id)
            .join(Account, Entry.account_id == Account.id)
            .where(
                Account.user_id == DEMO_USER_ID,
                Posting.category.in_(["groceries", "eating_out"]),
                Posting.business_date.between(start, end),
            )
        )
        return int(total or 0)

    recent = food(TODAY - timedelta(days=29), TODAY)
    before = food(TODAY - timedelta(days=59), TODAY - timedelta(days=30))

    assert before > 0
    assert 1.15 <= recent / before <= 1.25


def test_university_is_a_registered_institution_and_a_verified_payee(session: Session) -> None:
    institution = session.get_one(Institution, 1)
    payee = session.get_one(Payee, 1)

    assert institution.name == "Shenzhen Polytechnic International University"
    assert institution.name_local == "深圳国际理工大学"
    assert institution.country == "CN"
    assert institution.official_account_ref == "4100 2026 0000 8815"
    assert institution.official_bank_name == "Shenzhen Bay Commercial Bank (深圳湾商业银行)"
    assert payee.account_ref == institution.official_account_ref
    assert payee.institution_id == institution.id
    assert payee.verified_source == "institution_registry"
    assert payee.first_paid_at == TODAY - timedelta(days=60)


def test_upcoming_bills(session: Session) -> None:
    bills = session.scalars(select(Bill).order_by(Bill.due_date)).all()

    assert [(bill.payee.name, bill.amount_minor, bill.currency, bill.due_date, bill.status) for bill in bills] == [
        ("PearlTel Mobile", 9_800, "CNY", date(2026, 10, 28), "open"),
        ("Lingnan Student Housing", 280_000, "CNY", date(2026, 11, 1), "open"),
    ]


def test_the_one_transfer_service_is_marked_simulated(session: Session) -> None:
    providers = session.scalars(select(Provider)).all()

    assert len(providers) == 1
    provider = providers[0]
    assert provider.name == "RemitFast (simulated)"
    assert (provider.fee_fixed_minor, provider.fee_currency) == (800, "MYR")
    assert (provider.fee_pct, provider.markup_pct, provider.delivery_hours) == ("0", "1.2", 4)
    assert provider.simulated is True


def test_insight_is_computed_from_the_data(session: Session) -> None:
    insights = analyse_spending(session, session.get_one(User, DEMO_USER_ID), TODAY)
    eating_out = next(item for item in insights.categories if item.category == "eating_out")

    assert eating_out.change_pct is not None and eating_out.change_pct > 0
    assert insights.insight == f"Eating out is up {eating_out.change_pct}% compared with the previous 30 days."


def test_start_up_keeps_a_current_database(session: Session) -> None:
    session.get_one(User, DEMO_USER_ID).preferred_language = "zh"
    session.commit()
    session.close()

    ensure_seeded()

    with Session(get_engine()) as fresh:
        assert fresh.get_one(User, DEMO_USER_ID).preferred_language == "zh"


def test_start_up_rebuilds_a_database_from_before_the_audit_log(session: Session) -> None:
    # A volume seeded by an earlier version: data is there, but the chain was never started.
    session.execute(text("DROP TABLE audit_log"))
    session.execute(text("CREATE TABLE audit_log (seq INTEGER PRIMARY KEY, created_at DATETIME, event_type VARCHAR, "
                         "actor VARCHAR, payload JSON, prev_hash VARCHAR, hash VARCHAR)"))
    session.get_one(User, DEMO_USER_ID).preferred_language = "zh"
    session.commit()
    session.close()

    ensure_seeded()

    with Session(get_engine()) as fresh:
        assert fresh.get_one(User, DEMO_USER_ID).preferred_language == "en"
        assert [row.event_type for row in fresh.query(AuditLog).order_by(AuditLog.seq)] == ["system.genesis", "system.reset"]
        # The rebuilt table has its append-only protection again.
        triggers = fresh.execute(text("SELECT name FROM sqlite_master WHERE type = 'trigger' ORDER BY name")).scalars().all()
        assert triggers == ["audit_log_no_delete", "audit_log_no_update"]


def test_start_up_rebuilds_a_database_with_a_missing_column_or_table(session: Session) -> None:
    session.close()
    with get_engine().begin() as connection:
        connection.execute(text("ALTER TABLE providers DROP COLUMN delivery_hours"))
    ensure_seeded()
    with Session(get_engine()) as fresh:
        assert fresh.get_one(Provider, 1).delivery_hours == 4

    with get_engine().begin() as connection:
        connection.execute(text("DROP TABLE chat_messages"))
    ensure_seeded()
    with get_engine().connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM chat_messages")).scalar() == 0
