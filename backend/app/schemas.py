"""Request and response models for the HTTP API."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config import AgentMode
from app.money import Currency

Language = Literal["ms", "en", "zh"]
FxSource = Literal["frankfurter", "offline_snapshot"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    agent_mode: AgentMode
    demo_today: date
    version: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    preferred_language: Language
    home_currency: Currency
    per_txn_limit_minor: int
    daily_limit_minor: int
    new_payee_limit_minor: int


class LanguageUpdate(BaseModel):
    preferred_language: Language


class RateOut(BaseModel):
    """A frozen mid-market rate: `mid_rate` units of `quote` per 1 `base`."""

    base: Currency
    quote: Currency
    mid_rate: str
    source: FxSource
    fetched_at: datetime


class AccountOut(BaseModel):
    id: int
    currency: Currency
    name: str
    balance_minor: int
    home_equivalent_minor: int
    rate: RateOut | None  # None for the home-currency wallet


class AccountsOut(BaseModel):
    home_currency: Currency
    fx_source: FxSource
    accounts: list[AccountOut]


class AmountOut(BaseModel):
    currency: Currency
    amount_minor: int  # signed, from the user's side


class TransactionOut(BaseModel):
    id: int
    business_date: date
    created_at: datetime
    kind: str
    category: str | None
    category_label: str
    counterparty: str | None
    description: str
    amounts: list[AmountOut]


class CategorySpendOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str
    label: str
    currency: Currency
    total_minor: int
    previous_total_minor: int
    change_pct: int | None
    home_equivalent_minor: int


class ForecastOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: Currency
    as_of: date
    month_end: date
    balance_minor: int
    bills_due_minor: int
    projected_spending_minor: int
    forecast_minor: int


class SpendingInsightsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    home_currency: Currency
    period_days: int
    period_start: date
    period_end: date
    categories: list[CategorySpendOut]
    forecast: ForecastOut
    insight: str


class BillOut(BaseModel):
    id: int
    payee_id: int
    payee_name: str
    amount_minor: int
    currency: Currency
    due_date: date
    due_in_days: int  # counted from the demo date; negative when overdue
    late_fee_terms: str | None
    status: Literal["open", "paid", "cancelled"]


class PayeeOut(BaseModel):
    id: int
    name: str
    account_ref: str
    bank_name: str
    institution_id: int | None
    institution_name: str | None
    verified_source: Literal["institution_registry", "past_payment", "manual"] | None
    created_at: datetime
    first_paid_at: date | None
    cooling_off_until: datetime | None


class ResetOut(BaseModel):
    status: Literal["reset"]
    demo_today: date
    fx_source: FxSource


class ReasonOut(BaseModel):
    code: str
    severity: Literal["info", "warn", "block"]
    title: dict[str, str]  # by language: en, ms, zh
    text: dict[str, str]


class ActionOut(BaseModel):
    id: int
    plan_id: str | None
    tool: str
    args: dict[str, Any]
    tier: Literal["T2", "T3", "REFUSED"]
    status: str
    requires: list[str]  # subset of confirm, otp, cooling_off
    reasons: list[ReasonOut]
    cost_breakdown: dict[str, Any] | None
    otp_attempts: int
    otp_attempts_left: int
    created_at: datetime
    expires_at: datetime | None  # approval deadline while waiting for the student
    cooling_off_until: datetime | None  # when a cooling-off action will run
    executed_posting_id: int | None


class OtpIn(BaseModel):
    code: str = Field(min_length=1, max_length=12)


class OtpOut(BaseModel):
    accepted: bool
    attempts_left: int
    action: ActionOut


class AuditEntryOut(BaseModel):
    seq: int
    created_at: datetime
    event_type: str
    label: str
    actor: str
    summary: str
    payload: Any
    prev_hash: str
    hash: str


class EventTypeOut(BaseModel):
    code: str
    label: str


class AuditPageOut(BaseModel):
    total: int
    page: int
    page_size: int
    event_types: list[EventTypeOut]  # every event type, for the filter
    entries: list[AuditEntryOut]


class AuditVerifyOut(BaseModel):
    ok: bool
    entries: int | None = None
    broken_at: int | None = None
    expected_hash: str | None = None
    stored_hash: str | None = None


class TamperIn(BaseModel):
    seq: int | None = None


class TamperOut(BaseModel):
    """What changing one field does, on a copy. The real log is not changed."""

    seq: int
    event_type: str
    field: str
    original: Any
    tampered: Any
    verification: AuditVerifyOut
    entries: list[AuditEntryOut]  # the copy, around the changed entry
