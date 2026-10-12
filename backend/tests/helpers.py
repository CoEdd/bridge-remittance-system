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

# The model named in the developer's .env, read before the fixtures clear it. The tests that
# call the real API use it; every other test sees the built-in default.
CHOSEN_MODEL = __import__("os").environ.get("LLM_MODEL")

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
        kind="message",
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


# ---------------------------------------------------------------- chat turns through the API


def read_events(client: Any, stream_id: str) -> list[tuple[str, dict[str, Any]]]:
    """Every Server-Sent Event of one turn, as (event name, data)."""
    import json

    response = client.get(f"/chat/stream/{stream_id}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events, name = [], ""
    for line in response.text.splitlines():
        if line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            events.append((name, json.loads(line[5:])))
    return events


def say(client: Any, text: str) -> list[tuple[str, dict[str, Any]]]:
    """Send a chat message and collect the whole turn."""
    return read_events(client, client.post("/chat", json={"text": text}).json()["stream_id"])


def only(events: list[tuple[str, dict[str, Any]]], name: str) -> list[dict[str, Any]]:
    return [data for event, data in events if event == name]


def wallet_balances(client: Any) -> dict[str, int]:
    return {account["currency"]: account["balance_minor"] for account in client.get("/accounts").json()["accounts"]}


def all_audit_events(client: Any) -> list[dict[str, Any]]:
    """The whole audit log through the API, oldest first."""
    entries: list[dict[str, Any]] = []
    page = 1
    while True:
        body = client.get("/audit", params={"page": page, "page_size": 200}).json()
        entries += body["entries"]
        if len(entries) >= body["total"]:
            return entries[::-1]
        page += 1


# ---------------------------------------------------------------- a stand-in for the Anthropic client


class StandInClient:
    """Answers like the Anthropic client would, with canned answers. Records what it was sent."""

    def __init__(self, *answers: Any) -> None:
        from types import SimpleNamespace

        self.answers = list(answers)
        self.requests: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=self)
        self.messages = self

    def create(self, **request: Any) -> Any:
        import json
        from types import SimpleNamespace

        # Keep the conversation as it was at this moment: the driver goes on appending to its list.
        self.requests.append({**request, "messages": list(request.get("messages", []))})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, SimpleNamespace):
            return answer
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(answer))])
