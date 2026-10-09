"""
Demo events: things that happen TO the student during the demo.

They live in seed/ because, like the seed data, they are scripted facts written
straight to the ledger. Only this package and actions/executor.py may post.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.clock import demo_today
from app.db import write_lock
from app.ledger import income_legs, post
from app.models import Posting, User
from app.money import to_minor

STRANGER_NAME = "Zhou Wei"
STRANGER_AMOUNT = to_minor("3000.00", "CNY")


def stranger_sends_money(session: Session, user: User, now: datetime) -> Posting:
    """Act 3: CNY 3,000.00 arrives from someone the student has never dealt with."""
    with write_lock:
        posting = post(
            session,
            kind="income",
            legs=income_legs(session, user.id, "CNY", STRANGER_AMOUNT),
            business_date=demo_today(),
            created_at=now,
            category="transfer_in",
            counterparty=STRANGER_NAME,
            description="Inbound transfer",
        )
        session.commit()
        return posting
