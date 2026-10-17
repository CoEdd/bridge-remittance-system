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
    agent_mode: AgentMode  # the mode in effect
    # Set when the mode in effect is not the one asked for, e.g. "no API key".
    agent_note: str | None = None
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
    due_date: date | None  # a payment request from a message may have none
    due_in_days: int | None  # counted from the demo date; negative when overdue
    late_fee_terms: str | None
    reference: str | None = None
    status: Literal["open", "paid", "cancelled"]
    document_id: int | None
    flagged: bool  # its document is untrusted or carries a risk signal


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


DemoStepKey = Literal["upload", "verify", "plan", "pay", "agent", "mule", "audit", "redteam", "sources"]


class DemoStepOut(BaseModel):
    key: DemoStepKey
    done: bool


class DemoStateOut(BaseModel):
    """How far the demo has come, for the presenter's demo bar. Read from the app's own state."""

    steps: list[DemoStepOut]
    invoice_document_id: int | None  # the tuition invoice, once it has been taken in
    pending_plan_id: str | None  # a plan waiting for approval


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
    why: dict[str, str]  # why it has this tier, in plain words, by language
    cost_breakdown: dict[str, Any] | None
    otp_attempts: int
    otp_attempts_left: int
    created_at: datetime
    expires_at: datetime | None  # approval deadline while waiting for the student
    cooling_off_until: datetime | None  # when a cooling-off action will run
    executed_posting_id: int | None
    closed_at: datetime | None = None  # when it was executed, refused, cancelled or expired
    audit_seq: int | None = None  # the audit entry that recorded that


class ReceiptOut(BaseModel):
    """The receipt of an executed sandbox payment."""

    receipt_number: str
    business_date: date
    executed_at: datetime
    from_account: str
    payee_name: str
    payee_account: str
    payee_verified: str | None
    amount_minor: int
    currency: Currency
    reference: str | None
    status: str
    audit_seq: int
    audit_hash: str


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


DocumentStatus = Literal["verified", "needs_review", "untrusted", "risk_found"]


class DemoDocumentOut(BaseModel):
    key: str
    filename: str
    kind: Literal["invoice", "message"]
    label: str


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)
    sender: str | None = Field(default=None, max_length=80)  # who sent it, if the student says


class DocumentSummaryOut(BaseModel):
    id: int
    filename: str
    kind: Literal["invoice", "message"]
    languages: list[str]
    created_at: datetime
    status: DocumentStatus
    sender: str | None = None


class FieldOut(BaseModel):
    name: str
    value: str
    source: str  # the exact text the value came from
    start: int  # offsets of `source` in the document's raw text
    end: int
    verified: bool
    note: str | None  # why it is unverified


class HiddenTextOut(BaseModel):
    kind: str  # hidden_text | tiny_text | instruction_phrase | invisible_characters
    text: str


class ClauseVersionOut(BaseModel):
    text: str
    title: str | None
    file: str


class PolicyClauseOut(BaseModel):
    """The policy clause found by retrieval, plus the same clause in each published language."""

    text: str
    title: str | None
    file: str
    language: str
    institution: str | None = None
    versions: dict[str, ClauseVersionOut] = {}


class RiskSignalOut(BaseModel):
    code: str
    title: dict[str, str]  # by language: en, ms, zh
    text: dict[str, str]
    evidence: list[str]
    policy_clause: PolicyClauseOut | None = None


class DocumentOut(DocumentSummaryOut):
    raw_text: str
    trust_flag: Literal["trusted", "untrusted"]
    fields: list[FieldOut]
    hidden_text: list[HiddenTextOut]
    risk_signals: list[RiskSignalOut]
    explanation: dict[str, str]  # by language: ms, en, zh
    bill: BillOut | None
    # The neuro-symbolic claim check: origin, claims with status and evidence, conclusions with reasoning.
    claim_check: dict[str, Any] = {}


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ChatStartOut(BaseModel):
    stream_id: str  # follow the turn at GET /chat/stream/{stream_id}
    text: str  # the student's side of the turn, as it is stored


class ChatMessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    text: str
    text_en: str | None
    language: str
    created_at: datetime
    # On an assistant message: the turn's events, each {"event": name, "data": {...}}.
    events: list[dict[str, Any]] = []


class DemoSettingsOut(BaseModel):
    """Sandbox settings the screens show, so nothing is hardcoded in the frontend."""

    otp: str  # the one-time code Tier 3 approvals ask for in the demo
    cooling_off_seconds: int


class MuleEventOut(BaseModel):
    """The money-mule demo event: an inbound transfer from a stranger, then their message."""

    posting_id: int
    sender: str
    amount_minor: int
    currency: Currency
    document: DocumentOut


class NamedReasonOut(BaseModel):
    code: str
    title: str


class ToolOut(BaseModel):
    name: str
    label: str


class TierOut(BaseModel):
    tier: Literal["T0", "T1", "T2", "T3", "REFUSED"]
    name: str
    rule: str
    tools: list[ToolOut]  # the tools that start at this tier
    raised_by: list[NamedReasonOut]  # the reasons that put an action in this tier


class LimitOut(BaseModel):
    key: str
    label: str
    amount_minor: int | None  # in the home currency; None for a limit that is a time
    seconds: int | None
    effect: str  # what happens above it


class SafeguardOut(BaseModel):
    key: str
    title: str
    text: str
    reasons: list[NamedReasonOut]  # the reason codes this safeguard gives


class SecurityPolicyOut(BaseModel):
    """What the Security page shows, generated from the policy engine's own tables."""

    tiers: list[TierOut]
    currency: Currency  # of the limits
    limits: list[LimitOut]
    safeguards: list[SafeguardOut]


class RedTeamCaseOut(BaseModel):
    id: str
    title: str  # a name of two or three words
    attack: str  # what is tried, in one line
    expected: str


class RuleOut(BaseModel):
    """One rule of the claim check, in words."""

    id: str
    severity: Literal["block", "warn"]
    raises: str  # the policy reason it adds
    title: dict[str, str]  # by language: en, ms, zh
    text: dict[str, str]


class ClaimCheckOverviewOut(BaseModel):
    rules: list[RuleOut]
    # The latest results of `make eval-claims`, or None when it has not been run.
    evaluation: dict[str, Any] | None


# ---------------------------------------------------------------- rule sources


class SourceCounts(BaseModel):
    proposed: int = 0
    approved: int = 0
    rejected: int = 0
    needs_review: int = 0


class SourceOut(BaseModel):
    id: int
    kind: Literal["url", "upload", "bundled"]
    title: str
    url: str | None
    domain: str | None
    fetched_at: datetime
    dropped: int  # proposals the checks threw away
    counts: SourceCounts


class SourceItemOut(BaseModel):
    id: int
    source_id: int
    predicate: Literal["official_account", "official_channel", "policy", "known_scam_pattern"]
    label: str  # "Scam pattern", "Institution policy", ...
    institution: str
    value: str
    words: dict[str, str]  # the item in plain words, by language
    description: str
    examples: list[str]
    sentence: str
    link: str | None  # the page, scrolled to the sentence where the browser supports it
    confidence: float | None
    model: str | None
    status: Literal["proposed", "approved", "rejected", "needs_review"]
    edited: bool
    reviewer: str | None
    reviewed_at: datetime | None


class SourceDetailOut(SourceOut):
    items: list[SourceItemOut]


class SourcesOut(BaseModel):
    can_add: bool  # adding needs live mode
    note: str | None
    sources: list[SourceOut]


class SourceIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


class SourceItemEdit(BaseModel):
    institution: str | None = None
    value: str | None = None
    description: str | None = None
    examples: list[str] | None = None


class Choice(BaseModel):
    name: str
    label: str


class VocabularyOut(BaseModel):
    predicates: list[Choice]
    policies: list[Choice]
    patterns: list[Choice]
    institutions: list[str]

