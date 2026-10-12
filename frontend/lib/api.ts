import type {
  Accounts,
  Action,
  AuditFilters,
  AuditPage,
  AuditVerify,
  Bill,
  ChatMessage,
  ChatStart,
  ClaimCheckOverview,
  DemoDocument,
  DemoSettings,
  DocumentDetail,
  DocumentSummary,
  Health,
  Language,
  MuleEvent,
  OtpResult,
  Payee,
  RedTeamCase,
  RedTeamEvent,
  SecurityPolicy,
  SpendingInsights,
  TamperResult,
  Transaction,
  TransactionFilters,
  User,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** A failed backend call. `status` is null when the backend could not be reached. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // Not JSON: fall through to the generic message.
  }
  return `The backend answered with status ${response.status}.`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError("The backend could not be reached.", null);
  }
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status);
  }
  return (await response.json()) as T;
}

function postJson<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/**
 * POSTs and reads the answer as Server-Sent Events, calling `onEvent` for each one.
 * (The browser's EventSource can only GET.) Resolves when the stream ends.
 */
async function postForEvents(
  path: string,
  onEvent: (name: string, data: unknown) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, { method: "POST", headers: { Accept: "text/event-stream" }, signal });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError("The backend could not be reached.", null);
  }
  if (!response.ok || !response.body) throw new ApiError(await errorMessage(response), response.status);

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    // Events are separated by a blank line.
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const lines = block.split(/\r?\n/);
      const name = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
      const data = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (name && data) onEvent(name, JSON.parse(data));
    }
  }
}

function withQuery(path: string, params: object): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}

export const api = {
  health: (signal?: AbortSignal) => request<Health>("/health", { signal }),
  me: (signal?: AbortSignal) => request<User>("/me", { signal }),
  updateLanguage: (language: Language) =>
    request<User>("/me", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preferred_language: language }),
    }),
  accounts: (signal?: AbortSignal) => request<Accounts>("/accounts", { signal }),
  transactions: (filters: TransactionFilters = {}, signal?: AbortSignal) =>
    request<Transaction[]>(withQuery("/transactions", filters), { signal }),
  spending: (signal?: AbortSignal) => request<SpendingInsights>("/insights/spending", { signal }),
  bills: (signal?: AbortSignal) => request<Bill[]>("/bills", { signal }),
  payees: (signal?: AbortSignal) => request<Payee[]>("/payees", { signal }),
  audit: (filters: AuditFilters = {}, signal?: AbortSignal) =>
    request<AuditPage>(withQuery("/audit", filters), { signal }),
  verifyAudit: () => request<AuditVerify>("/audit/verify"),
  simulateTamper: () => request<TamperResult>("/audit/simulate-tamper", { method: "POST" }),
  /** Link to download the whole audit log. */
  auditExportUrl: (format: "json" | "csv") => `${BASE_URL}/audit/export?format=${format}`,
  documents: (signal?: AbortSignal) => request<DocumentSummary[]>("/documents", { signal }),
  document: (id: number, signal?: AbortSignal) => request<DocumentDetail>(`/documents/${id}`, { signal }),
  demoDocuments: (signal?: AbortSignal) => request<DemoDocument[]>("/demo/documents", { signal }),
  ingestDemoDocument: (key: string) => request<DocumentDetail>(`/demo/documents/${key}`, { method: "POST" }),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentDetail>("/documents", { method: "POST", body: form });
  },
  pasteMessage: (text: string) => postJson<DocumentDetail>("/documents/message", { text }),
  /** Every action the agent proposed that needed the student or was refused, oldest first. */
  actions: (signal?: AbortSignal) => request<Action[]>("/actions", { signal }),
  confirmAction: (id: number) => postJson<Action>(`/actions/${id}/confirm`),
  submitOtp: (id: number, code: string) => postJson<OtpResult>(`/actions/${id}/otp`, { code }),
  cancelAction: (id: number) => postJson<Action>(`/actions/${id}/cancel`),
  chatHistory: (signal?: AbortSignal) => request<ChatMessage[]>("/chat/history", { signal }),
  /** Start a turn. Follow it with `followTurn` from lib/chat. */
  sendChat: (text: string) => postJson<ChatStart>("/chat", { text }),
  /** Start a turn in which the agent reads and explains a document. */
  chatAboutDocument: (id: number) => postJson<ChatStart>(`/chat/document/${id}`),
  chatStreamUrl: (streamId: string) => `${BASE_URL}/chat/stream/${streamId}`,
  demoSettings: (signal?: AbortSignal) => request<DemoSettings>("/demo/settings", { signal }),
  /** Demo event: a stranger sends money, then their "please forward it" message arrives. */
  strangerTransfer: () => postJson<MuleEvent>("/demo/events/mule"),
  securityPolicy: (signal?: AbortSignal) => request<SecurityPolicy>("/security/policy", { signal }),
  redTeamCases: (signal?: AbortSignal) => request<RedTeamCase[]>("/security/redteam", { signal }),
  claimCheckOverview: (signal?: AbortSignal) => request<ClaimCheckOverview>("/security/claim-check", { signal }),
  /** Runs the red-team suite on isolated copies of the database, reporting each case as it starts and ends. */
  runRedTeam: (onEvent: (event: RedTeamEvent) => void, signal?: AbortSignal) =>
    postForEvents("/security/redteam/run", (name, data) => onEvent({ event: name, data } as RedTeamEvent), signal),
};
