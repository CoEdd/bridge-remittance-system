from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ledger import (
    InsufficientFundsError,
    LedgerError,
    Leg,
    UnbalancedPostingError,
    conversion_legs,
    fee_legs,
    income_legs,
    payment_legs,
    post,
    system_account,
    user_account,
)
from app.models import Account, Entry, Posting
from app.seed import DEMO_USER_ID

TODAY = date(2026, 10, 15)
NOW = datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)


def balance(session: Session, name: str) -> int:
    return session.scalars(select(Account.balance_minor).where(Account.name == name)).one()


def per_currency_totals(posting: Posting) -> dict[str, int]:
    totals: dict[str, int] = {}
    for entry in posting.entries:
        totals[entry.currency] = totals.get(entry.currency, 0) + entry.amount_minor
    return totals


def posting_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Posting)) or 0


def test_income_balances_and_moves_the_balances(session: Session) -> None:
    before_user = balance(session, "MYR wallet")
    before_income = balance(session, "external_income_MYR")

    posting = post(
        session,
        kind="income",
        legs=income_legs(session, DEMO_USER_ID, "MYR", 250_000),
        business_date=TODAY,
        created_at=NOW,
        description="Stipend",
    )

    assert per_currency_totals(posting) == {"MYR": 0}
    assert balance(session, "MYR wallet") == before_user + 250_000
    assert balance(session, "external_income_MYR") == before_income - 250_000


@pytest.mark.parametrize("kind", ["payment", "expense"])
def test_payment_and_expense_balance(session: Session, kind: str) -> None:
    before_user = balance(session, "CNY wallet")
    before_external = balance(session, "external_payments_CNY")

    posting = post(
        session,
        kind=kind,
        legs=payment_legs(session, DEMO_USER_ID, "CNY", 120_000),
        business_date=TODAY,
        created_at=NOW,
        description="Sample",
    )

    assert per_currency_totals(posting) == {"CNY": 0}
    assert balance(session, "CNY wallet") == before_user - 120_000
    assert balance(session, "external_payments_CNY") == before_external + 120_000


def test_conversion_with_fee_balances_in_both_currencies(session: Session) -> None:
    before = {name: balance(session, name) for name in ("MYR wallet", "CNY wallet")}

    posting = post(
        session,
        kind="conversion",
        legs=conversion_legs(
            session,
            DEMO_USER_ID,
            sell_currency="MYR",
            sell_minor=100_000,
            fee_minor=800,
            buy_currency="CNY",
            buy_minor=160_056,
        ),
        business_date=TODAY,
        created_at=NOW,
        description="Convert MYR to CNY",
    )

    assert per_currency_totals(posting) == {"MYR": 0, "CNY": 0}
    assert len(posting.entries) == 5
    assert balance(session, "MYR wallet") == before["MYR wallet"] - 100_800
    assert balance(session, "CNY wallet") == before["CNY wallet"] + 160_056
    assert balance(session, "fx_clearing_MYR") == 100_000
    assert balance(session, "fees_MYR") == 800
    assert balance(session, "fx_clearing_CNY") == -160_056


def test_fee_and_seed_postings_balance(session: Session) -> None:
    fee = post(
        session,
        kind="fee",
        legs=fee_legs(session, DEMO_USER_ID, "MYR", 800),
        business_date=TODAY,
        created_at=NOW,
        description="Transfer fee",
    )
    seed = post(
        session,
        kind="seed",
        legs=income_legs(session, DEMO_USER_ID, "USD", 1_000),
        business_date=TODAY,
        created_at=NOW,
        description="Opening balance",
    )

    assert per_currency_totals(fee) == {"MYR": 0}
    assert per_currency_totals(seed) == {"USD": 0}


def test_unbalanced_posting_is_rejected_and_nothing_is_saved(session: Session) -> None:
    count = posting_count(session)
    before = balance(session, "CNY wallet")
    wallet = user_account(session, DEMO_USER_ID, "CNY")
    external = system_account(session, "external_payments", "CNY")

    with pytest.raises(UnbalancedPostingError):
        post(
            session,
            kind="payment",
            legs=[Leg(wallet.id, -10_000), Leg(external.id, 9_999)],
            business_date=TODAY,
            created_at=NOW,
            description="Off by one fen",
        )
    session.commit()

    assert posting_count(session) == count
    assert balance(session, "CNY wallet") == before


def test_amounts_that_cancel_across_currencies_are_still_rejected(session: Session) -> None:
    # -100 MYR and +100 CNY sum to zero as plain numbers, but not within each currency.
    myr = user_account(session, DEMO_USER_ID, "MYR")
    cny = user_account(session, DEMO_USER_ID, "CNY")

    with pytest.raises(UnbalancedPostingError):
        post(
            session,
            kind="conversion",
            legs=[Leg(myr.id, -10_000), Leg(cny.id, 10_000)],
            business_date=TODAY,
            created_at=NOW,
            description="Not a real conversion",
        )


def test_a_user_account_cannot_go_below_zero(session: Session) -> None:
    count = posting_count(session)
    too_much = balance(session, "USD wallet") + 1

    with pytest.raises(InsufficientFundsError):
        post(
            session,
            kind="payment",
            legs=payment_legs(session, DEMO_USER_ID, "USD", too_much),
            business_date=TODAY,
            created_at=NOW,
            description="More than he has",
        )

    assert posting_count(session) == count


@pytest.mark.parametrize(
    "legs",
    [
        [Leg(1, -100)],  # one entry only
        [Leg(1, 0), Leg(2, 0)],  # zero entries
        [Leg(1, -100), Leg(999_999, 100)],  # unknown account
        [Leg(1, -100.0), Leg(13, 100.0)],  # floats  # type: ignore[arg-type]
    ],
)
def test_malformed_postings_are_rejected(session: Session, legs: list[Leg]) -> None:
    with pytest.raises(LedgerError):
        post(session, kind="payment", legs=legs, business_date=TODAY, created_at=NOW, description="Bad")


def test_unknown_posting_kind_is_rejected(session: Session) -> None:
    with pytest.raises(LedgerError):
        post(
            session,
            kind="gift",
            legs=income_legs(session, DEMO_USER_ID, "MYR", 100),
            business_date=TODAY,
            created_at=NOW,
            description="Bad kind",
        )


def test_cached_balances_equal_the_sum_of_entries(session: Session) -> None:
    # After the seeded history plus one posting of every shape.
    post(session, kind="income", legs=income_legs(session, DEMO_USER_ID, "MYR", 250_000),
         business_date=TODAY, created_at=NOW, description="Stipend")  # fmt: skip
    post(session, kind="conversion", business_date=TODAY, created_at=NOW, description="Convert",
         legs=conversion_legs(session, DEMO_USER_ID, sell_currency="MYR", sell_minor=100_000,
                              fee_minor=800, buy_currency="CNY", buy_minor=160_056))  # fmt: skip
    post(session, kind="payment", legs=payment_legs(session, DEMO_USER_ID, "CNY", 120_000),
         business_date=TODAY, created_at=NOW, description="Bill")  # fmt: skip
    post(session, kind="fee", legs=fee_legs(session, DEMO_USER_ID, "MYR", 800),
         business_date=TODAY, created_at=NOW, description="Fee")  # fmt: skip
    session.commit()

    sums = dict(
        session.execute(select(Entry.account_id, func.sum(Entry.amount_minor)).group_by(Entry.account_id)).all()
    )
    accounts = session.scalars(select(Account)).all()

    assert len(accounts) == 15
    for account in accounts:
        assert account.balance_minor == sums.get(account.id, 0), account.name


def test_the_whole_ledger_sums_to_zero_in_each_currency(session: Session) -> None:
    totals = session.execute(select(Entry.currency, func.sum(Entry.amount_minor)).group_by(Entry.currency)).all()

    assert sorted(totals) == [("CNY", 0), ("MYR", 0), ("USD", 0)]
