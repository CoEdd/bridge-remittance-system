"use client";

import clsx from "clsx";
import {
  ArrowLeftRight,
  Banknote,
  Calculator,
  ChartColumn,
  ChevronDown,
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

const ICONS: Record<string, LucideIcon> = {
  get_balances: Wallet,
  get_transactions: List,
  analyse_spending: ChartColumn,
  read_document: FileText,
  get_fx_rate: ArrowLeftRight,
  get_transfer_quote: Calculator,
  plan_funding: ClipboardList,
  verify_payee: UserCheck,
  convert_currency: ArrowLeftRight,
  pay_bill: Banknote,
  add_payee: UserPlus,
  explain_decision: CircleHelp,
};

interface Verdict {
  label: string;
  className: string;
}

const VERDICTS: Record<StepEvent["verdict"], Verdict> = {
  allowed: { label: "Allowed", className: "text-teal" },
  pending: { label: "Waiting for your approval", className: "text-amber-ink" },
  refused: { label: "Refused", className: "text-danger" },
};

// What became of a step that had to wait for the student.
const OUTCOMES: Partial<Record<Action["status"], Verdict>> = {
  cooling_off: { label: "Approved, cooling off", className: "text-amber-ink" },
  executed: { label: "Approved and done", className: "text-teal" },
  refused: { label: "Refused", className: "text-danger" },
  cancelled: { label: "Cancelled", className: "text-muted" },
  expired: { label: "Expired", className: "text-muted" },
};

export function tierOf(tier: StepEvent["tier"]): Tier {
  return tier === "REFUSED" ? "Blocked" : tier;
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

interface StepCardProps {
  step: StepEvent;
  /** For a step that waited for the student: the action as it stands now. */
  action?: Action;
}

/** One tool call of the agent: what it did, its tier and the verdict. Opens to show the details. */
export function StepCard({ step, action }: StepCardProps) {
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const Icon = ICONS[step.tool] ?? Wrench;
  const verdict = (step.verdict === "pending" && action && OUTCOMES[action.status]) || VERDICTS[step.verdict];
  const inputs = inputRows(step);
  const results = resultRows(step);

  return (
    <div className="rounded-card border border-line bg-surface motion-safe:animate-step-in">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen(!open)}
        className="grid w-full grid-cols-[auto_1fr_auto] items-center gap-3 rounded-card px-4 py-2 text-left transition-colors duration-150 hover:bg-paper"
      >
        <Icon aria-hidden className="size-5 text-muted" strokeWidth={1.75} />
        <span className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
          <span className="text-15 font-medium text-ink">{step.label}</span>
          <span className="flex items-center gap-2">
            <TierBadge tier={tierOf(step.tier)} />
            <span className={clsx("text-13 font-medium", verdict.className)}>{verdict.label}</span>
          </span>
        </span>
        <ChevronDown
          aria-hidden
          className={clsx("size-4 text-muted transition-transform duration-150", open && "rotate-180")}
        />
      </button>
      {open && (
        <div id={panelId} className="flex flex-col gap-3 border-t border-line px-4 py-3">
          {step.summary && <p className="text-13 text-body">{step.summary}</p>}
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
      )}
    </div>
  );
}
