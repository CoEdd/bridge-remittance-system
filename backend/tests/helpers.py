"""Small builders for test data. Tests may write to the ledger directly; app code may not."""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ledger import income_legs, payment_legs, post
from app.models import Account, AuditLog, Bill, Document, Entry, Payee, Posting, User
from app.money import to_minor
from app.policy import Context
from app.seed import DEMO_USER_ID

TODAY = date(2026, 10, 15)
NOW = datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc)
LONG_AGO = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)

# Seeded ids.
MYR_WALLET, CNY_WALLET, USD_WALLET = 1, 2, 3
UNIVERSITY, LANDLORD, PHONE_COMPANY = 1, 2, 3
RENT_BILL, PHONE_BILL = 1, 2
PROVIDER = 1
OTP = "246810"


def cny(amount: str) -> int:
    return to_minor(amount, "CNY")


def myr(amount: str) -> int:
    return to_minor(amount, "MYR")


def the_user(session: Session) -> User:
    return session.get_one(User, DEMO_USER_ID)


def context(session: Session, now: datetime = NOW, action_id: int | None = None) -> Context:
    return Context(session=session, today=TODAY, now=now, action_id=action_id)


def balance(session: Session, account_id: int) -> int:
    return session.scalars(select(Account.balance_minor).where(Account.id == account_id)).one()


def balances(session: Session) -> dict[str, int]:
    rows = session.execute(select(Account.currency, Account.balance_minor).where(Account.user_id == DEMO_USER_ID))
    return {currency: amount for currency, amount in rows}


def fund(session: Session, currency: str, amount_minor: int, when: datetime = LONG_AGO) -> None:
    """Give Ahmad more money, long enough ago that no rule treats it as a recent inbound transfer."""
    post(
        session,
        kind="income",
        legs=income_legs(session, DEMO_USER_ID, currency, amount_minor),
        business_date=when.date(),
        created_at=when,
        counterparty="Monthly stipend",
        description="Test funding",
    )
    session.commit()


def spend(session: Session, currency: str, amount_minor: int) -> None:
    """Take money out of a wallet (an everyday expense, not a bill payment)."""
    post(
        session,
        kind="expense",
        legs=payment_legs(session, DEMO_USER_ID, currency, amount_minor),
        business_date=TODAY,
        created_at=NOW,
        description="Test spending",
    )
    session.commit()


def inbound(
    session: Session, amount_minor: int, currency: str = "CNY", sender: str | None = "Zhang W.", when: datetime = NOW
) -> Posting:
    """An inbound transfer, as a stranger's 'mistaken' payment would arrive."""
    posting = post(
        session,
        kind="income",
        legs=income_legs(session, DEMO_USER_ID, currency, amount_minor),
        business_date=TODAY,
        created_at=when,
        counterparty=sender,
        description="Inbound transfer",
    )
    session.commit()
    return posting


def new_payee(session: Session, name: str = "Chen Li", created_at: datetime = LONG_AGO) -> Payee:
    payee = Payee(
        user_id=DEMO_USER_ID,
        name=name,
        account_ref="6222 0000 1111 2222",
        bank_name="Example Bank",
        created_at=created_at,
    )
    session.add(payee)
    session.commit()
    return payee


def new_document(session: Session, trust_flag: str = "trusted", risk_signals: list[Any] | None = None) -> Document:
    document = Document(
        user_id=DEMO_USER_ID,
        filename="fixture.txt",
        source_language="en",
        raw_text="fixture",
        chars_meta=[],
        extracted_fields={},
        trust_flag=trust_flag,
        risk_signals=risk_signals or [],
        explanation={},
        created_at=LONG_AGO,
    )
    session.add(document)
    session.commit()
    return document


def new_bill(
    session: Session,
    payee_id: int,
    amount: str,
    currency: str = "CNY",
    document: Document | None = None,
    status: str = "open",
) -> Bill:
    bill = Bill(
        user_id=DEMO_USER_ID,
        payee_id=payee_id,
        document_id=document.id if document else None,
        amount_minor=to_minor(amount, currency),
        currency=currency,
        due_date=TODAY + timedelta(days=30),
        status=status,
    )
    session.add(bill)
    session.commit()
    return bill


def pay_args(bill: Bill | int, **extra: Any) -> dict[str, Any]:
    bill_id = bill if isinstance(bill, int) else bill.id
    return {"bill_id": bill_id, "from_account_id": CNY_WALLET, **extra}


def convert_args(amount_minor: int, **extra: Any) -> dict[str, Any]:
    return {
        "from_currency": "MYR",
        "to_currency": "CNY",
        "amount_minor": amount_minor,
        "provider_id": PROVIDER,
        **extra,
    }


def audit_events(session: Session, after_seq: int = 0) -> list[str]:
    return list(
        session.scalars(select(AuditLog.event_type).where(AuditLog.seq > after_seq).order_by(AuditLog.seq))
    )


def last_audit(session: Session, event_type: str) -> AuditLog:
    return session.scalars(
        select(AuditLog).where(AuditLog.event_type == event_type).order_by(AuditLog.seq.desc()).limit(1)
    ).one()


def audit_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(AuditLog)) or 0


def posting_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Posting)) or 0


def ledger_is_consistent(session: Session) -> bool:
    """Every currency sums to zero and every cached balance equals its entries."""
    totals = session.execute(select(Entry.currency, func.sum(Entry.amount_minor)).group_by(Entry.currency)).all()
    sums = dict(session.execute(select(Entry.account_id, func.sum(Entry.amount_minor)).group_by(Entry.account_id)).all())
    accounts = session.scalars(select(Account)).all()
    return all(total == 0 for _, total in totals) and all(
        account.balance_minor == sums.get(account.id, 0) for account in accounts
    )
