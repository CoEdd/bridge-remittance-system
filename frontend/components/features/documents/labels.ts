import type { BadgeTone } from "@/components/ui/Badge";
import type { DocumentKind, DocumentStatus, Language } from "@/lib/types";

export const KIND_LABELS: Record<DocumentKind, string> = { invoice: "Invoice", message: "Message" };

export const LANGUAGE_LABELS: Record<Language, string> = { en: "English", ms: "Malay", zh: "Chinese" };

export const STATUS: Record<DocumentStatus, { label: string; tone: BadgeTone }> = {
  verified: { label: "Verified", tone: "success" },
  needs_review: { label: "Needs review", tone: "neutral" },
  risk_found: { label: "Risk found", tone: "warning" },
  untrusted: { label: "Untrusted", tone: "danger" },
};

export const FIELD_LABELS: Record<string, string> = {
  issuer: "Issuer",
  issuer_local_name: "Local name",
  payee_name: "Payee",
  payee_account: "Account",
  bank_name: "Bank",
  amount: "Amount",
  currency: "Currency",
  due_date: "Due date",
  late_fee_terms: "Late fee",
  invoice_number: "Invoice number",
};

export function languageList(languages: Language[]): string {
  return languages.map((code) => LANGUAGE_LABELS[code] ?? code).join(", ");
}
