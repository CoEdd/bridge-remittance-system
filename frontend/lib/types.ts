export type AgentMode = "live" | "scripted";

export type Currency = "MYR" | "CNY" | "USD";

export type Language = "ms" | "en" | "zh";

export type FxSource = "frankfurter" | "offline_snapshot";

/** Response of GET /health. */
export interface Health {
  status: "ok";
  agent_mode: AgentMode;
  /** Why the mode differs from the one asked for, e.g. "no API key". Otherwise null. */
  agent_note: string | null;
  /** Demo business date, YYYY-MM-DD. */
  demo_today: string;
  version: string;
}

/** Response of GET /me. Limits are in minor units of the home currency. */
export interface User {
  id: number;
  name: string;
  preferred_language: Language;
  home_currency: Currency;
  per_txn_limit_minor: number;
  daily_limit_minor: number;
  new_payee_limit_minor: number;
}

/** A frozen mid-market rate: `mid_rate` units of `quote` per 1 `base`. */
export interface Rate {
  base: Currency;
  quote: Currency;
  /** Decimal as text, e.g. "1.6381". */
  mid_rate: string;
  source: FxSource;
  /** UTC timestamp. */
  fetched_at: string;
}

export interface Account {
  id: number;
  currency: Currency;
  name: string;
  balance_minor: number;
  home_equivalent_minor: number;
  /** null for the home-currency wallet. */
  rate: Rate | null;
}

/** Response of GET /accounts. */
export interface Accounts {
  home_currency: Currency;
  fx_source: FxSource;
  accounts: Account[];
}

export interface TransactionAmount {
  currency: Currency;
  /** Signed, from the user's side: negative is money out. */
  amount_minor: number;
}

export interface Transaction {
  id: number;
  /** YYYY-MM-DD on the demo clock. */
  business_date: string;
  created_at: string;
  kind: string;
  category: string | null;
  category_label: string;
  counterparty: string | null;
  description: string;
  amounts: TransactionAmount[];
}

export interface TransactionFilters {
  currency?: Currency;
  category?: string;
  days?: number;
  limit?: number;
}

export interface CategorySpend {
  category: string;
  label: string;
  currency: Currency;
  total_minor: number;
  previous_total_minor: number;
  /** Whole percent against the previous period; null when there is nothing to compare. */
  change_pct: number | null;
  home_equivalent_minor: number;
}

export interface Forecast {
  currency: Currency;
  as_of: string;
  month_end: string;
  balance_minor: number;
  bills_due_minor: number;
  projected_spending_minor: number;
  forecast_minor: number;
}

/** Response of GET /insights/spending. */
export interface SpendingInsights {
  home_currency: Currency;
  period_days: number;
  period_start: string;
  period_end: string;
  categories: CategorySpend[];
  forecast: Forecast;
  /** One sentence computed by the backend from the data. */
  insight: string;
}

export interface Bill {
  id: number;
  payee_id: number;
  payee_name: string;
  amount_minor: number;
  currency: Currency;
  /** null for a payment request that names no date. */
  due_date: string | null;
  /** Counted from the demo date; negative when overdue. */
  due_in_days: number | null;
  late_fee_terms: string | null;
  status: "open" | "paid" | "cancelled";
  document_id: number | null;
  /** Its document is untrusted or carries a risk signal. */
  flagged: boolean;
}

export interface Payee {
  id: number;
  name: string;
  account_ref: string;
  bank_name: string;
  institution_id: number | null;
  institution_name: string | null;
  verified_source: "institution_registry" | "past_payment" | "manual" | null;
  created_at: string;
  first_paid_at: string | null;
  cooling_off_until: string | null;
}

export interface AuditEntry {
  seq: number;
  /** Real UTC time. */
  created_at: string;
  event_type: string;
  /** Readable name of the event type. */
  label: string;
  actor: "agent" | "policy" | "user" | "system";
  summary: string;
  payload: unknown;
  prev_hash: string;
  hash: string;
}

export interface AuditEventType {
  code: string;
  label: string;
}

/** Response of GET /audit: newest first. */
export interface AuditPage {
  total: number;
  page: number;
  page_size: number;
  event_types: AuditEventType[];
  entries: AuditEntry[];
}

export interface AuditFilters {
  page?: number;
  page_size?: number;
  event_type?: string;
  /** Ask for one entry by its number. */
  seq?: number;
}

/** Response of GET /audit/verify. */
export interface AuditVerify {
  ok: boolean;
  entries: number | null;
  broken_at: number | null;
  expected_hash: string | null;
  stored_hash: string | null;
}

/** Response of POST /audit/simulate-tamper: what one changed field does, on a copy. */
export interface TamperResult {
  seq: number;
  event_type: string;
  field: string;
  original: unknown;
  tampered: unknown;
  verification: AuditVerify;
  /** The copy, around the changed entry, newest first. */
  entries: AuditEntry[];
}

export type DocumentKind = "invoice" | "message";
export type DocumentStatus = "verified" | "needs_review" | "untrusted" | "risk_found";

/** One bundled demo document, for the "Use a demo document" menu. */
export interface DemoDocument {
  key: string;
  filename: string;
  kind: DocumentKind;
  label: string;
}

export interface DocumentSummary {
  id: number;
  filename: string;
  kind: DocumentKind;
  languages: Language[];
  created_at: string;
  status: DocumentStatus;
}

export interface DocumentField {
  name: string;
  value: string;
  /** The exact text the value came from. */
  source: string;
  /** Offsets of `source` in the document's raw text. */
  start: number;
  end: number;
  verified: boolean;
  /** Why it is unverified. */
  note: string | null;
}

export interface PolicyClause {
  /** The clause as retrieval found it. */
  text: string;
  title: string | null;
  file: string;
  language: Language;
  institution: string | null;
  /** The same clause in each language the policy is published in. */
  versions: Partial<Record<Language, { text: string; title: string | null; file: string }>>;
}

/** Text by language. */
export type Translations = Record<Language, string>;

export interface RiskSignal {
  code: string;
  title: Translations;
  text: Translations;
  evidence: string[];
  policy_clause: PolicyClause | null;
}

export interface DocumentDetail extends DocumentSummary {
  raw_text: string;
  trust_flag: "trusted" | "untrusted";
  fields: DocumentField[];
  hidden_text: { kind: string; text: string }[];
  risk_signals: RiskSignal[];
  explanation: Translations;
  bill: Bill | null;
}

export type PolicyTier = "T0" | "T1" | "T2" | "T3" | "REFUSED";

/** A policy reason, with its text in every language. */
export interface Reason {
  code: string;
  severity: "info" | "warn" | "block";
  title: Translations;
  text: Translations;
}

/** What a conversion costs, as the policy engine computed it. */
export interface ConversionCost {
  kind: "conversion";
  provider_name: string;
  from_currency: Currency;
  to_currency: Currency;
  amount_minor: number;
  mid_rate: string;
  offered_rate: string;
  markup_pct: string;
  fee_minor: number;
  /** Cost hidden in the exchange rate, in `from_currency`. */
  markup_cost_minor: number;
  total_cost_minor: number;
  total_debit_minor: number;
  amount_received_minor: number;
  arrives_at: string;
  /** "simulated": there are no real payment rails. */
  source: string;
  expires_at: string;
  warning: string | null;
}

export interface PaymentCost {
  kind: "payment";
  bill_id: number;
  payee_id: number;
  payee_name: string;
  payee_account_ref: string;
  amount_minor: number;
  currency: Currency;
  fee_minor: number;
  total_minor: number;
}

export type CostBreakdown = ConversionCost | PaymentCost;

export type ActionStatus =
  | "awaiting_confirm"
  | "awaiting_otp"
  | "cooling_off"
  | "executed"
  | "refused"
  | "cancelled"
  | "expired";

export type ApprovalStep = "confirm" | "otp" | "cooling_off";

/** A money action the agent proposed: waiting for the student, finished, or refused. */
export interface Action {
  id: number;
  plan_id: string | null;
  tool: string;
  args: Record<string, unknown>;
  tier: "T2" | "T3" | "REFUSED";
  status: ActionStatus;
  requires: ApprovalStep[];
  reasons: Reason[];
  /** Why it has this tier, in plain words. */
  why: Translations;
  cost_breakdown: CostBreakdown | null;
  otp_attempts_left: number;
  created_at: string;
  /** Approval deadline while waiting for the student. */
  expires_at: string | null;
  /** When a cooling-off action will run. */
  cooling_off_until: string | null;
  executed_posting_id: number | null;
  /** When it was executed, refused, cancelled or expired. */
  closed_at: string | null;
  /** The audit entry that recorded that. */
  audit_seq: number | null;
}

/** Response of POST /actions/{id}/otp. */
export interface OtpResult {
  accepted: boolean;
  attempts_left: number;
  action: Action;
}

/** One tool call of the agent, as streamed by the chat. */
export interface StepEvent {
  id: number;
  tool: string;
  label: string;
  tier: PolicyTier;
  verdict: "allowed" | "pending" | "refused";
  summary: string;
  /** Why it got this tier, in the student's language and in English. */
  why: string;
  why_en: string;
  input: Record<string, unknown>;
  details: Record<string, unknown>;
}

export interface AgentReply {
  text: string;
  text_en: string;
  language: Language;
}

export interface ApprovalEvent {
  plan_id: string;
  actions: { id: number; tool: string; tier: PolicyTier; summary: string }[];
}

export interface BlockedReason {
  code: string;
  title: string;
  text: string;
  title_en: string;
  text_en: string;
  evidence: string[];
  policy_clause: PolicyClause | null;
}

export interface BlockedEvent {
  action_id: number;
  tool: string;
  reasons: BlockedReason[];
  advice: string;
  advice_en: string;
  audit_seq: number | null;
}

export interface ChatErrorEvent {
  message: string;
  message_en: string;
}

/** An event of one chat turn, as stored with the reply and as streamed. */
export type TurnEvent =
  | { event: "step"; data: StepEvent }
  | { event: "approval_required"; data: ApprovalEvent }
  | { event: "blocked"; data: BlockedEvent }
  | { event: "error"; data: ChatErrorEvent };

/** Response of POST /chat and POST /chat/document/{id}. */
export interface ChatStart {
  /** Follow the turn with `followTurn`. */
  stream_id: string;
  /** The student's side of the turn, as the backend stores it. */
  text: string;
}

/** One row of GET /chat/history. */
export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
  text_en: string | null;
  language: Language;
  created_at: string;
  events: TurnEvent[];
}

/** Response of GET /demo/settings. */
export interface DemoSettings {
  /** The one-time code Tier 3 approvals ask for in the demo. */
  otp: string;
  cooling_off_seconds: number;
}

/** Response of POST /demo/events/mule. */
export interface MuleEvent {
  posting_id: number;
  sender: string;
  amount_minor: number;
  currency: Currency;
  document: DocumentDetail;
}
