"use client";

import clsx from "clsx";
import {
  ArrowLeftRight,
  Banknote,
  Calculator,
  ChartColumn,
  CircleHelp,
  ClipboardList,
  FileText,
  List,
  UserCheck,
  UserPlus,
  Wallet,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { useId, useState } from "react";
import { inputRows, resultRows, type Row } from "@/components/features/assistant/details";
import { TierBadge, type Tier } from "@/components/ui/Badge";
import type { Action, StepEvent } from "@/lib/types";

// A word or two per tool: the strip shows what the agent did at a glance.
const TOOLS: Record<string, { name: string; icon: LucideIcon }> = {
  get_balances: { name: "Balances", icon: Wallet },
  get_transactions: { name: "Transactions", icon: List },
  analyse_spending: { name: "Spending", icon: ChartColumn },
  read_document: { name: "Read", icon: FileText },
  get_fx_rate: { name: "Rate", icon: ArrowLeftRight },
  get_transfer_quote: { name: "True cost", icon: Calculator },
  plan_funding: { name: "Plan", icon: ClipboardList },
  verify_payee: { name: "Payee check", icon: UserCheck },
  convert_currency: { name: "Convert", icon: ArrowLeftRight },
  pay_bill: { name: "Pay", icon: Banknote },
  add_payee: { name: "Add payee", icon: UserPlus },
  explain_decision: { name: "Why", icon: CircleHelp },
};

const TONES = {
  plain: "border-line bg-surface text-body hover:bg-paper",
  waiting: "border-amber-line bg-amber-tint text-amber-ink",
  done: "border-teal bg-teal-tint text-ink",
  blocked: "border-danger bg-danger-tint text-danger",
};

// What became of a step that had to wait for the student.
const OUTCOMES: Record<Action["status"], { word: string; tone: keyof typeof TONES }> = {
  awaiting_confirm: { word: "Waiting", tone: "waiting" },
  awaiting_otp: { word: "Waiting", tone: "waiting" },
  cooling_off: { word: "Cooling off", tone: "waiting" },
  executed: { word: "Done", tone: "done" },
  refused: { word: "Refused", tone: "blocked" },
  cancelled: { word: "Cancelled", tone: "plain" },
  expired: { word: "Expired", tone: "plain" },
};

export function tierOf(tier: StepEvent["tier"]): Tier {
  return tier === "REFUSED" ? "Blocked" : tier;
}

/** The state of a step right now: a word (none for a plain allowed step) and its colour. */
function stateOf(step: StepEvent, action: Action | undefined): { word: string | null; tone: keyof typeof TONES } {
  if (step.verdict === "refused") return { word: "Blocked", tone: "blocked" };
  if (step.verdict === "pending") return action ? OUTCOMES[action.status] : { word: "Waiting", tone: "waiting" };
  return { word: null, tone: "plain" };
}

/** A two-column table of plain lines. `strong` names the lines that matter most. */
export function Rows({ rows, strong = [], size = "13" }: { rows: Row[]; strong?: string[]; size?: "13" | "15" }) {
  return (
    <dl className={clsx("grid grid-cols-[auto_1fr] gap-x-4", size === "15" ? "gap-y-2 text-15" : "gap-y-1 text-13")}>
      {rows.map(([label, value]) => (
        <div key={label} className={clsx("contents", strong.includes(label) && "font-semibold")}>
          <dt className={strong.includes(label) ? "text-ink" : "text-muted"}>{label}</dt>
          <dd className="text-right break-words text-ink tabular-nums">{value || "None"}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Everything about one step, shown when its pill is clicked. */
function StepDetails({ step, id }: { step: StepEvent; id: string }) {
  const inputs = inputRows(step);
  const results = resultRows(step);
  return (
    <div id={id} className="mt-2 flex flex-col gap-3 rounded-card border border-line bg-surface p-4">
      <p className="flex items-center justify-between gap-3 text-15 font-medium text-ink">
        {step.label}
        <TierBadge tier={tierOf(step.tier)} />
      </p>
      {inputs.length > 0 && (
        <section>
          <h4 className="mb-1 text-13 font-medium text-muted">Asked for</h4>
          <Rows rows={inputs} />
        </section>
      )}
      {results.length > 0 && (
        <section>
          <h4 className="mb-1 text-13 font-medium text-muted">Result</h4>
          <Rows rows={results} />
        </section>
      )}
      <p className="text-13 text-body">
        <span className="font-medium text-ink">Why? </span>
        {step.why}
        {step.why_en !== step.why && (
          <span lang="en" className="block text-muted">
            {step.why_en}
          </span>
        )}
      </p>
      <details>
        <summary className="cursor-pointer rounded-sm text-13 font-medium text-muted">Raw data</summary>
        <pre
          tabIndex={0}
          className="mt-2 max-h-56 overflow-auto rounded-control border border-line bg-paper p-3 text-13 text-ink"
        >
          {JSON.stringify({ input: step.input, result: step.details }, null, 2)}
        </pre>
      </details>
    </div>
  );
}

interface StepsProps {
  steps: StepEvent[];
  /** The current state of every action, to show what became of a step that waited. */
  actions: Action[];
}

/**
 * What the agent did in one turn: a strip of small pills, one per tool call, each with its
 * tier. Clicking a pill shows that step's details underneath.
 */
export function Steps({ steps, actions }: StepsProps) {
  const panelId = useId();
  const [opened, setOpened] = useState<number | null>(null);
  if (steps.length === 0) return null;
  const shown = steps.find((step) => step.id === opened);

  return (
    <div>
      <ul aria-label="Steps" className="flex flex-wrap gap-1">
        {steps.map((step) => {
          const tool = TOOLS[step.tool] ?? { name: step.tool, icon: Wrench };
          const state = stateOf(step, actions.find((action) => action.id === step.details.action_id));
          const open = step.id === opened;
          return (
            <li key={step.id} className="motion-safe:animate-step-in">
              <button
                type="button"
                aria-expanded={open}
                aria-controls={open ? panelId : undefined}
                title={step.label}
                onClick={() => setOpened(open ? null : step.id)}
                className={clsx(
                  "inline-flex h-7 items-center gap-1 rounded-full border px-2 text-13 font-medium transition-colors duration-150",
                  TONES[state.tone],
                  open && "outline-2 outline-offset-1 outline-teal",
                )}
              >
                <tool.icon aria-hidden className="size-3.5" strokeWidth={1.75} />
                {tool.name}
                {step.tier !== "REFUSED" && (
                  <>
                    <span aria-hidden className="font-normal opacity-80">
                      {step.tier}
                    </span>
                    <span className="sr-only">Tier {step.tier.slice(1)}</span>
                  </>
                )}
                {state.word && <span>· {state.word}</span>}
              </button>
            </li>
          );
        })}
      </ul>
      {shown && <StepDetails step={shown} id={panelId} />}
    </div>
  );
}
