import { FIELD_LABELS } from "@/components/features/documents/labels";
import { formatAmount, formatDate, formatTimestampUtc } from "@/lib/format";
import type { ConversionCost, CostBreakdown, Currency, PaymentCost, StepEvent } from "@/lib/types";

/** One line of a details table. */
export type Row = [label: string, value: string];

type Json = Record<string, unknown>;

const CURRENCIES: readonly string[] = ["MYR", "CNY", "USD"];

function record(value: unknown): Json {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? (value as Json) : {};
}

function list(value: unknown): Json[] {
  return Array.isArray(value) ? value.map(record) : [];
}

function text(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

function money(minor: unknown, currency: unknown): string {
  if (typeof minor !== "number" || !Number.isSafeInteger(minor) || !CURRENCIES.includes(text(currency))) return "";
  return formatAmount(minor, currency as Currency);
}

/** "12000.00" -> 1200000, without floating point. */
function toMinor(decimal: string): number | null {
  const match = /^(\d+)(?:\.(\d{2}))?$/.exec(decimal);
  return match ? Number(match[1]) * 100 + Number(match[2] ?? "0") : null;
}

function day(value: unknown): string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) ? formatDate(value) : "";
}

/** The cost breakdown the policy engine attached to a money step, if it is one this screen knows. */
export function asCost(value: unknown): CostBreakdown | null {
  const kind = record(value).kind;
  return kind === "conversion" || kind === "payment" ? (value as CostBreakdown) : null;
}

/** Every number behind a conversion: the fee, and what the exchange rate costs on top. */
export function conversionRows(cost: ConversionCost): Row[] {
  const from = cost.from_currency;
  return [
    ["Amount", formatAmount(cost.amount_minor, from)],
    ["Transfer service", cost.provider_name],
    ["Mid-market rate", `1 ${from} = ${cost.mid_rate} ${cost.to_currency}`],
    ["Offered rate", `1 ${from} = ${cost.offered_rate} ${cost.to_currency}`],
    ["Fee", formatAmount(cost.fee_minor, from)],
    ["Cost hidden in the rate", formatAmount(cost.markup_cost_minor, from)],
    ["True cost", formatAmount(cost.total_cost_minor, from)],
    ["You receive", formatAmount(cost.amount_received_minor, cost.to_currency)],
    ["Arrives", formatTimestampUtc(cost.arrives_at)],
    ["Quote expires", formatTimestampUtc(cost.expires_at)],
  ];
}

export function paymentRows(cost: PaymentCost): Row[] {
  return [
    ["Amount", formatAmount(cost.amount_minor, cost.currency)],
    ["Payee", cost.payee_name],
    ["Account", cost.payee_account_ref],
    ["Fee", formatAmount(cost.fee_minor, cost.currency)],
    ["Total", formatAmount(cost.total_minor, cost.currency)],
  ];
}

export function costRows(cost: CostBreakdown): Row[] {
  return cost.kind === "conversion" ? conversionRows(cost) : paymentRows(cost);
}

const NEEDS: Record<string, string> = {
  confirm: "your confirmation",
  otp: "a one-time code",
  cooling_off: "a short wait",
};

const INPUT_LABELS: Record<string, string> = {
  bill_id: "Bill",
  document_id: "Document",
  payee_id: "Payee",
  action_id: "Action",
  from_account_id: "From wallet",
  provider_id: "Transfer service",
  from_currency: "From",
  to_currency: "To",
  base: "From",
  quote: "To",
  currency: "Currency",
  category: "Category",
  days: "Days",
  limit: "Limit",
  name: "Name",
  account_ref: "Account",
  bank_name: "Bank",
};

/** What the agent asked the tool for. */
export function inputRows(step: StepEvent): Row[] {
  const input = step.input;
  return Object.entries(input).flatMap(([key, value]): Row[] => {
    if (value === null || typeof value === "object") return [];
    if (key === "amount_minor" || key === "amount_source_minor") {
      return [["Amount", money(value, input.from_currency) || text(value)]];
    }
    const label = INPUT_LABELS[key] ?? key;
    return [[label, key.endsWith("_id") ? `#${text(value)}` : text(value)]];
  });
}

/** What the tool found or what the policy engine decided, as readable lines. */
export function resultRows(step: StepEvent): Row[] {
  const details = step.details;
  if (typeof details.error === "string") return [["Problem", details.error]];

  const cost = asCost(details.cost_breakdown) ?? asCost(details);
  if (cost) {
    const needs = Array.isArray(details.requires) ? details.requires.map((item) => NEEDS[text(item)] ?? text(item)) : [];
    return needs.length > 0 ? [...costRows(cost), ["Needs", needs.join(", ")]] : costRows(cost);
  }

  switch (step.tool) {
    case "get_balances":
      return list(details.accounts).map((account) => [
        `${text(account.currency)} wallet`,
        money(account.balance_minor, account.currency),
      ]);
    case "plan_funding":
      return [
        ...list(details.counted_bills).map(
          (bill): Row => [
            text(bill.payee_name),
            [money(bill.amount_minor, details.currency), day(bill.due_date) && `due ${day(bill.due_date)}`]
              .filter(Boolean)
              .join(" · "),
          ],
        ),
        ["Buffer", money(details.buffer_minor, details.currency)],
        ["Needed", money(details.required_minor, details.currency)],
        ["In the wallet", money(details.balance_minor, details.currency)],
        ["Short by", money(details.shortfall_minor, details.currency)],
      ];
    case "read_document": {
      const signals = Array.isArray(details.risk_signals) ? details.risk_signals.map(text) : [];
      const fields = record(details.verified_fields);
      const shown = (name: string, value: unknown): string => {
        if (name === "amount") return money(toMinor(text(value)), fields.currency) || text(value);
        return (name === "due_date" && day(value)) || text(value);
      };
      return [
        ...Object.entries(fields).map(([name, value]): Row => [FIELD_LABELS[name] ?? name, shown(name, value)]),
        ["Hidden text", details.hidden_text_found ? "Found" : "None"],
        ["Risk signals", signals.length > 0 ? signals.join(", ") : "None"],
      ];
    }
    case "verify_payee":
      return [
        ["Payee", text(details.name)],
        ["Account", text(details.account_ref)],
        ["Bank", text(details.bank_name)],
        ["Official account", details.is_official_account ? "Yes" : "No"],
        ["Paid before", day(details.first_paid_at) || "No"],
      ];
    case "analyse_spending":
      return list(details.categories)
        .slice(0, 5)
        .map((item): Row => {
          const change = typeof item.change_pct === "number" ? ` (${item.change_pct > 0 ? "+" : ""}${item.change_pct}%)` : "";
          return [text(item.label), `${money(item.total_minor, item.currency)}${change}`];
        });
    case "get_fx_rate":
      return [
        ["Rate", `1 ${text(details.base)} = ${text(details.mid_rate)} ${text(details.quote)}`],
        ["Source", text(details.source) || "Same currency"],
      ];
    case "get_transactions":
      return list(details.transactions)
        .slice(0, 5)
        .map((item): Row => [
          `${day(item.business_date)} · ${text(item.counterparty) || text(item.description)}`,
          list(item.amounts)
            .map((part) => money(part.amount_minor, part.currency))
            .join(", "),
        ]);
    case "explain_decision":
      return [
        ["Action", `#${text(details.action_id)}`],
        ["Status", text(details.status).replace(/_/g, " ")],
        ["Why", text(details.why)],
      ];
    default:
      return Object.entries(details)
        .filter(([, value]) => value !== null && typeof value !== "object")
        .map(([key, value]): Row => [key, text(value)]);
  }
}
