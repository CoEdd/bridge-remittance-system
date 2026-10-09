import type {
  Accounts,
  AuditFilters,
  AuditPage,
  AuditVerify,
  Bill,
  DemoDocument,
  DocumentDetail,
  DocumentSummary,
  Health,
  Language,
  Payee,
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
  pasteMessage: (text: string) =>
    request<DocumentDetail>("/documents/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }),
};
