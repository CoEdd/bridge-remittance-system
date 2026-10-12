import { formatAmount } from "@/lib/format";
import type {
  Action,
  AgentReply,
  Bill,
  ChatMessage,
  DemoDocument,
  DocumentSummary,
  Language,
  Translations,
  TurnEvent,
} from "@/lib/types";

/** One exchange: what the student said or shared, what the agent did, and its reply. */
export interface Turn {
  key: string;
  userText: string;
  events: TurnEvent[];
  reply: AgentReply | null;
  /** "streaming" while the agent works; "lost" when the connection broke first. */
  state: "streaming" | "done" | "lost";
}

/** The stored chat as turns. A user message is followed by the assistant message that answers it. */
export function turnsFromHistory(messages: ChatMessage[]): Turn[] {
  const turns: Turn[] = [];
  for (const message of messages) {
    if (message.role === "user") {
      turns.push({ key: `m${message.id}`, userText: message.text, events: [], reply: null, state: "done" });
      continue;
    }
    const turn = turns[turns.length - 1];
    if (!turn || turn.reply) continue;
    turn.events = message.events;
    turn.reply = { text: message.text, text_en: message.text_en ?? message.text, language: message.language };
  }
  return turns;
}

export function isWaiting(action: Action): boolean {
  return action.status === "awaiting_confirm" || action.status === "awaiting_otp" || action.status === "cooling_off";
}

/** "Convert MYR 7,483.64 to CNY 11,978.01" or "Pay CNY 12,000.00 to the university". */
export function describeAction(action: Action): string {
  const cost = action.cost_breakdown;
  if (cost?.kind === "conversion") {
    const received = formatAmount(cost.amount_received_minor, cost.to_currency);
    return `Convert ${formatAmount(cost.amount_minor, cost.from_currency)} to ${received}`;
  }
  if (cost?.kind === "payment") return `Pay ${formatAmount(cost.amount_minor, cost.currency)} to ${cost.payee_name}`;
  return action.tool === "add_payee" ? "Add a payee" : action.tool;
}

/** The demo questions, in each language the student can choose. */
export const QUESTIONS: Record<"deadline" | "agent" | "forward", Translations> = {
  deadline: {
    ms: "Boleh saya bayar yuran ini sebelum tarikh akhir?",
    en: "Can I pay this fee before the deadline?",
    zh: "我能在截止日期前付这笔学费吗？",
  },
  agent: {
    ms: "Boleh saya bayar melalui ejen ini?",
    en: "Can I pay through this agent?",
    zh: "我可以通过这个代理付款吗？",
  },
  forward: {
    ms: "Boleh saya pindahkan wang ini seperti yang diminta?",
    en: "Can I forward this money as asked?",
    zh: "我可以按要求把这笔钱转给他吗？",
  },
};

/** The bundled documents the demo walks through, in order. */
const DEMO_ORDER = ["tuition_invoice", "agent_offer", "mule_message"] as const;
type DemoKey = (typeof DEMO_ORDER)[number];

const DEMO_CHIPS: Record<DemoKey, string> = {
  tuition_invoice: "Use demo: tuition invoice",
  agent_offer: "Use demo: agent message",
  mule_message: "Use demo: stranger's transfer",
};

export type Suggestion =
  | { kind: "upload"; label: string }
  | { kind: "demo"; label: string; demoKey: DemoKey }
  | { kind: "ask"; label: string; language: Language }
  | { kind: "approve"; label: string; planId: string }
  | { kind: "audit"; label: string };

interface SuggestionInput {
  documents: DocumentSummary[];
  bills: Bill[];
  actions: Action[];
  demos: DemoDocument[];
  language: Language;
}

/**
 * What to do next, worked out from what the backend already holds: the newest document,
 * its bill, and what has happened to that bill's payment.
 */
export function suggestNext({ documents, bills, actions, demos, language }: SuggestionInput): Suggestion[] {
  const filenameOf = (key: DemoKey) => demos.find((demo) => demo.key === key)?.filename;
  const isStranger = (document: DocumentSummary) => document.filename === filenameOf("mule_message");
  // How far the story has come. A pasted agent message counts the same as the bundled one.
  const reached: Record<DemoKey, boolean> = {
    tuition_invoice: documents.some((document) => document.kind === "invoice"),
    agent_offer: documents.some((document) => document.kind === "message" && !isStranger(document)),
    mule_message: documents.some(isStranger),
  };
  const nextDemo = DEMO_ORDER.find((key) => !reached[key]);
  const demoChip: Suggestion[] = nextDemo
    ? [{ kind: "demo", label: DEMO_CHIPS[nextDemo], demoKey: nextDemo }]
    : [{ kind: "audit", label: "View audit log" }];

  const latest = documents[0];
  if (!latest) return [{ kind: "upload", label: "Upload an invoice" }, ...demoChip];

  const waiting = actions.find(isWaiting);
  if (waiting?.plan_id) return [{ kind: "approve", label: "Review and approve", planId: waiting.plan_id }];

  const bill = bills.find((item) => item.document_id === latest.id);
  const blocked = actions.some(
    (action) => action.tool === "pay_bill" && action.args.bill_id === bill?.id && action.status === "refused",
  );
  if (!bill || bill.status !== "open" || blocked) return demoChip;

  const question = latest.kind === "invoice" ? "deadline" : isStranger(latest) ? "forward" : "agent";
  return [{ kind: "ask", label: QUESTIONS[question][language], language }];
}

const WORD_LIMIT = 40;
const CJK_LIMIT = 80;

/** The first 40 words of a reply (80 characters for Chinese), or null when it is short enough. */
export function shortened(text: string): string | null {
  if (!text.includes(" ")) return text.length > CJK_LIMIT ? `${text.slice(0, CJK_LIMIT)}…` : null;
  const words = text.split(/\s+/);
  return words.length > WORD_LIMIT ? `${words.slice(0, WORD_LIMIT).join(" ")}…` : null;
}
