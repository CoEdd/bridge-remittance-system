"""Database tables. All are created now, so later steps need no migrations."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DDL, JSON, CheckConstraint, ForeignKey, Text, event
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UtcDateTime

LANGUAGES = ("ms", "en", "zh")
ACCOUNT_KINDS = ("user", "system")
POSTING_KINDS = ("income", "expense", "conversion", "payment", "fee", "seed")
VERIFIED_SOURCES = ("institution_registry", "past_payment", "manual")
TRUST_FLAGS = ("trusted", "untrusted")
DOCUMENT_KINDS = ("invoice", "message")
BILL_STATUSES = ("open", "paid", "cancelled")
FX_SOURCES = ("frankfurter", "offline_snapshot")
ACTION_STATUSES = (
    "awaiting_confirm",
    "awaiting_otp",
    "cooling_off",
    "executed",
    "cancelled",
    "refused",
    "expired",
)
AUDIT_ACTORS = ("agent", "policy", "user", "system")
CHAT_ROLES = ("user", "assistant")


def one_of(column: str, values: tuple[str, ...]) -> CheckConstraint:
    """A CHECK constraint that limits a text column to the listed values (NULL passes)."""
    allowed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=f"{column}_allowed")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (one_of("preferred_language", LANGUAGES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    preferred_language: Mapped[str]
    home_currency: Mapped[str]
    # Limits are in minor units of the home currency (MYR-equivalent).
    per_txn_limit_minor: Mapped[int]
    daily_limit_minor: Mapped[int]
    new_payee_limit_minor: Mapped[int]


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        one_of("kind", ACCOUNT_KINDS),
        CheckConstraint("kind != 'user' OR balance_minor >= 0", name="user_balance_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # null: system account
    currency: Mapped[str]
    kind: Mapped[str]
    name: Mapped[str] = mapped_column(unique=True)
    # Cached sum of this account's entries. Only ledger.post() changes it.
    balance_minor: Mapped[int] = mapped_column(default=0)


class Posting(Base):
    __tablename__ = "postings"
    __table_args__ = (one_of("kind", POSTING_KINDS),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    business_date: Mapped[date]  # demo clock
    kind: Mapped[str]
    category: Mapped[str | None]
    counterparty: Mapped[str | None]
    description: Mapped[str]
    action_id: Mapped[int | None] = mapped_column(ForeignKey("pending_actions.id"))

    entries: Mapped[list["Entry"]] = relationship(back_populates="posting")


class Entry(Base):
    __tablename__ = "entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    posting_id: Mapped[int] = mapped_column(ForeignKey("postings.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    amount_minor: Mapped[int]  # signed: positive adds to the account
    currency: Mapped[str]

    posting: Mapped[Posting] = relationship(back_populates="entries")
    account: Mapped[Account] = relationship()


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    name_local: Mapped[str]
    country: Mapped[str]
    official_account_ref: Mapped[str]
    official_bank_name: Mapped[str]


class Payee(Base):
    __tablename__ = "payees"
    __table_args__ = (one_of("verified_source", VERIFIED_SOURCES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str]
    account_ref: Mapped[str]
    bank_name: Mapped[str]
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id"))
    verified_source: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    first_paid_at: Mapped[date | None]  # business date of the first payment
    cooling_off_until: Mapped[datetime | None] = mapped_column(UtcDateTime)

    institution: Mapped[Institution | None] = relationship()


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (one_of("trust_flag", TRUST_FLAGS), one_of("kind", DOCUMENT_KINDS))

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str]
    kind: Mapped[str]  # invoice (a file) or message (pasted text)
    source: Mapped[str] = mapped_column(default="upload")  # how it arrived: upload, paste, demo bundle, demo event
    source_language: Mapped[str]  # every language detected, comma-separated: "en,zh"
    raw_text: Mapped[str] = mapped_column(Text)
    chars_meta: Mapped[Any] = mapped_column(JSON)
    extracted_fields: Mapped[Any] = mapped_column(JSON)
    trust_flag: Mapped[str]
    risk_signals: Mapped[Any] = mapped_column(JSON)
    explanation: Mapped[Any] = mapped_column(JSON)  # one entry per language
    # The neuro-symbolic claim check: claims with their status, conclusions and reasoning chains.
    claim_check: Mapped[Any] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (one_of("status", BILL_STATUSES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"))
    payee_id: Mapped[int] = mapped_column(ForeignKey("payees.id"))
    amount_minor: Mapped[int]
    currency: Mapped[str]
    due_date: Mapped[date | None]  # a payment request in a message may have none
    late_fee_terms: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str]

    payee: Mapped[Payee] = relationship()
    document: Mapped[Document | None] = relationship()


class FxQuote(Base):
    __tablename__ = "fx_quotes"
    __table_args__ = (one_of("source", FX_SOURCES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    base: Mapped[str]
    quote: Mapped[str]
    mid_rate: Mapped[str]  # Decimal as text: units of `quote` per 1 `base`
    source: Mapped[str]
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime)

    @property
    def rate(self) -> Decimal:
        return Decimal(self.mid_rate)


class Provider(Base):
    __tablename__ = "providers"
    __table_args__ = (CheckConstraint("simulated = 1", name="provider_is_simulated"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    fee_fixed_minor: Mapped[int]
    fee_currency: Mapped[str]
    fee_pct: Mapped[str]  # Decimal as text, in percent
    markup_pct: Mapped[str]  # Decimal as text, in percent against the mid-market rate
    delivery_hours: Mapped[int]
    simulated: Mapped[bool] = mapped_column(default=True)  # always true: sandbox only


class PendingAction(Base):
    __tablename__ = "pending_actions"
    __table_args__ = (one_of("status", ACTION_STATUSES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    plan_id: Mapped[str | None]
    tool: Mapped[str]
    args: Mapped[Any] = mapped_column(JSON)
    tier: Mapped[str]
    status: Mapped[str]
    reasons: Mapped[Any] = mapped_column(JSON)
    cost_breakdown: Mapped[Any] = mapped_column(JSON)
    otp_attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    # When the current state ends. While awaiting confirmation or a code: the approval
    # deadline. While cooling off: the moment the wait is over and the action runs.
    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    # Id of the posting that executed this action. Postings point back with action_id;
    # this side has no foreign key so the two tables do not depend on each other.
    executed_posting_id: Mapped[int | None]


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (one_of("actor", AUDIT_ACTORS),)

    seq: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    event_type: Mapped[str]
    actor: Mapped[str]
    payload: Mapped[Any] = mapped_column(JSON)
    prev_hash: Mapped[str]
    hash: Mapped[str]


# The database itself refuses to change or remove audit entries.
for _operation in ("UPDATE", "DELETE"):
    event.listen(
        AuditLog.__table__,
        "after_create",
        DDL(
            f"CREATE TRIGGER audit_log_no_{_operation.lower()} BEFORE {_operation} ON audit_log "
            "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END"
        ),
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (one_of("role", CHAT_ROLES),)

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str]
    text: Mapped[str] = mapped_column(Text)
    text_en: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str]
    # On an assistant message: the turn's events (steps, approval_required, blocked, error),
    # so the conversation can be shown again exactly as it happened.
    events: Mapped[Any] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
