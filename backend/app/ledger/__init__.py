"""Double-entry ledger. Every posting balances to zero within each currency."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import POSTING_KINDS, Account, Entry, Posting

# One of each exists per currency, named "<role>_<currency>", e.g. "fees_MYR".
SYSTEM_ROLES = ("fx_clearing", "fees", "external_payments", "external_income")


class LedgerError(ValueError):
    """The posting was refused. Nothing was saved."""


class UnbalancedPostingError(LedgerError):
    pass


class InsufficientFundsError(LedgerError):
    pass


@dataclass(frozen=True)
class Leg:
    """One side of a posting. The currency is always the account's currency."""

    account_id: int
    amount_minor: int  # signed: positive adds to the account


def post(
    session: Session,
    *,
    kind: str,
    legs: Sequence[Leg],
    business_date: date,
    created_at: datetime,
    description: str,
    category: str | None = None,
    counterparty: str | None = None,
    action_id: int | None = None,
) -> Posting:
    """
    Save one posting and update the cached account balances in the same transaction.

    Refused unless the legs sum to zero within each currency, and unless every
    user account stays at or above zero. The caller commits.
    """
    if kind not in POSTING_KINDS:
        raise LedgerError(f"Unknown posting kind: {kind}.")
    if len(legs) < 2:
        raise LedgerError("A posting needs at least two entries.")
    for leg in legs:
        if isinstance(leg.amount_minor, bool) or not isinstance(leg.amount_minor, int):
            raise LedgerError("Entry amounts must be integers in minor units.")
        if leg.amount_minor == 0:
            raise LedgerError("An entry cannot be zero.")

    account_ids = {leg.account_id for leg in legs}
    accounts = {
        account.id: account
        for account in session.scalars(select(Account).where(Account.id.in_(account_ids)))
    }
    if len(accounts) != len(account_ids):
        raise LedgerError("A posting refers to an account that does not exist.")

    totals: dict[str, int] = defaultdict(int)
    changes: dict[int, int] = defaultdict(int)
    for leg in legs:
        totals[accounts[leg.account_id].currency] += leg.amount_minor
        changes[leg.account_id] += leg.amount_minor

    unbalanced = {currency: total for currency, total in totals.items() if total != 0}
    if unbalanced:
        raise UnbalancedPostingError(f"Entries do not sum to zero: {unbalanced}.")

    for account_id, change in changes.items():
        account = accounts[account_id]
        if account.kind == "user" and account.balance_minor + change < 0:
            raise InsufficientFundsError(f"{account.name} would go below zero.")

    posting = Posting(
        created_at=created_at,
        business_date=business_date,
        kind=kind,
        category=category,
        counterparty=counterparty,
        description=description,
        action_id=action_id,
        entries=[
            Entry(
                account_id=leg.account_id,
                amount_minor=leg.amount_minor,
                currency=accounts[leg.account_id].currency,
            )
            for leg in legs
        ],
    )
    session.add(posting)
    for account_id, change in changes.items():
        # A SQL-side increment, so the database adds to the current stored balance.
        accounts[account_id].balance_minor = Account.balance_minor + change  # type: ignore[assignment]
    session.flush()
    return posting


def system_account(session: Session, role: str, currency: str) -> Account:
    if role not in SYSTEM_ROLES:
        raise LedgerError(f"Unknown system account role: {role}.")
    return session.scalars(select(Account).where(Account.name == f"{role}_{currency}")).one()


def user_account(session: Session, user_id: int, currency: str) -> Account:
    return session.scalars(
        select(Account).where(Account.user_id == user_id, Account.currency == currency)
    ).one()


def _require_positive(*amounts: int) -> None:
    if any(isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0 for amount in amounts):
        raise LedgerError("Amounts must be positive integers in minor units.")


def income_legs(session: Session, user_id: int, currency: str, amount_minor: int) -> list[Leg]:
    """Money arriving from outside: external_income -x, user +x."""
    _require_positive(amount_minor)
    return [
        Leg(system_account(session, "external_income", currency).id, -amount_minor),
        Leg(user_account(session, user_id, currency).id, amount_minor),
    ]


def payment_legs(session: Session, user_id: int, currency: str, amount_minor: int) -> list[Leg]:
    """Money leaving to someone else (a payment or an expense): user -x, external_payments +x."""
    _require_positive(amount_minor)
    return [
        Leg(user_account(session, user_id, currency).id, -amount_minor),
        Leg(system_account(session, "external_payments", currency).id, amount_minor),
    ]


def fee_legs(session: Session, user_id: int, currency: str, fee_minor: int) -> list[Leg]:
    """A fee charged on its own: user -fee, fees +fee."""
    _require_positive(fee_minor)
    return [
        Leg(user_account(session, user_id, currency).id, -fee_minor),
        Leg(system_account(session, "fees", currency).id, fee_minor),
    ]


def conversion_legs(
    session: Session,
    user_id: int,
    *,
    sell_currency: str,
    sell_minor: int,
    fee_minor: int,
    buy_currency: str,
    buy_minor: int,
) -> list[Leg]:
    """
    A currency conversion with its fee charged in the sold currency:
    user sell -(amount + fee), fx_clearing sell +amount, fees sell +fee,
    fx_clearing buy -converted, user buy +converted.
    """
    _require_positive(sell_minor, buy_minor)
    if isinstance(fee_minor, bool) or not isinstance(fee_minor, int) or fee_minor < 0:
        raise LedgerError("A fee must be a non-negative integer in minor units.")
    if sell_currency == buy_currency:
        raise LedgerError("A conversion needs two different currencies.")
    legs = [
        Leg(user_account(session, user_id, sell_currency).id, -(sell_minor + fee_minor)),
        Leg(system_account(session, "fx_clearing", sell_currency).id, sell_minor),
        Leg(system_account(session, "fx_clearing", buy_currency).id, -buy_minor),
        Leg(user_account(session, user_id, buy_currency).id, buy_minor),
    ]
    if fee_minor:
        legs.insert(2, Leg(system_account(session, "fees", sell_currency).id, fee_minor))
    return legs
