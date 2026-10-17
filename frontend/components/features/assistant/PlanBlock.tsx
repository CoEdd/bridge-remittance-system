"use client";

import { ArrowRight, CircleCheck, ReceiptText } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { isWaiting } from "@/components/features/assistant/model";
import { ReceiptSheet } from "@/components/features/assistant/ReceiptSheet";
import { Rows } from "@/components/features/assistant/Steps";
import { Button } from "@/components/ui/Button";
import type { Row } from "@/components/features/assistant/details";
import { formatAmount, formatTimestampUtc } from "@/lib/format";
import { useLanguage } from "@/lib/language";
import type { Action, ApprovalEvent } from "@/lib/types";

const CLOSED_LABELS: Partial<Record<Action["status"], string>> = {
  cancelled: "Cancelled",
  expired: "Expired",
  refused: "Refused",
};

/** "Converted MYR 7,397.78 to CNY 11,978.00" or "Paid CNY 12,000.00 to the university". */
function done(action: Action): string {
  const cost = action.cost_breakdown;
  if (cost?.kind === "conversion") {
    const received = formatAmount(cost.amount_received_minor, cost.to_currency);
    return `Converted ${formatAmount(cost.amount_minor, cost.from_currency)} to ${received}`;
  }
  if (cost?.kind === "payment") return `Paid ${formatAmount(cost.amount_minor, cost.currency)} to ${cost.payee_name}`;
  return "Done";
}

function receiptRows(action: Action): Row[] {
  const cost = action.cost_breakdown;
  const rows: Row[] = [];
  if (cost?.kind === "conversion") rows.push(["Fee", formatAmount(cost.fee_minor, cost.from_currency)]);
  if (cost?.kind === "payment") rows.push(["Account", cost.payee_account_ref]);
  if (action.executed_posting_id !== null) rows.push(["Posting", `#${action.executed_posting_id}`]);
  if (action.closed_at) rows.push(["Time", formatTimestampUtc(action.closed_at)]);
  return rows;
}

/** Proof that an approved action ran, in one line. The posting, the time and the audit entry open on request. */
function Receipt({ action, onView }: { action: Action; onView: (id: number) => void }) {
  const payment = action.cost_breakdown?.kind === "payment";
  return (
    <details
      data-receipt
      className="rounded-card border border-teal bg-surface px-4 py-2 motion-safe:animate-step-in"
    >
      <summary className="flex cursor-pointer items-center gap-2 rounded-sm text-15 font-medium text-ink">
        <CircleCheck aria-hidden className="size-5 shrink-0 text-teal" />
        <span className="min-w-0 flex-1">{done(action)}</span>
        {payment ? (
          <Button
            variant="secondary"
            size="sm"
            icon={ReceiptText}
            onClick={(event) => {
              event.preventDefault(); // open the receipt, not the details below
              onView(action.id);
            }}
          >
            View receipt
          </Button>
        ) : (
          <span className="text-13 font-medium text-teal">Receipt</span>
        )}
      </summary>
      <div className="mt-2 border-t border-line pt-2">
        <Rows rows={receiptRows(action)} />
        {action.audit_seq !== null && (
          <Link
            href={`/audit?entry=${action.audit_seq}`}
            className="mt-2 inline-flex items-center gap-1 rounded-sm text-13 font-medium text-teal hover:underline"
          >
            Audit log
            <ArrowRight aria-hidden className="size-4" />
          </Link>
        )}
      </div>
    </details>
  );
}

interface PlanBlockProps {
  approval: ApprovalEvent;
  /** The current state of every action, from the backend. */
  actions: Action[];
}

/**
 * What became of the plan a turn proposed: a one-line receipt for each step that ran, and a
 * line for one that was cancelled, expired or refused. Steps still waiting show in the strip above.
 */
export function PlanBlock({ approval, actions }: PlanBlockProps) {
  const { language } = useLanguage();
  const [viewing, setViewing] = useState<number | null>(null);
  return (
    <>
      <ReceiptSheet actionId={viewing} onClose={() => setViewing(null)} />
      {approval.actions.map((card) => {
        const action = actions.find((item) => item.id === card.id);
        if (!action || isWaiting(action)) return null;
        if (action.status === "executed") return <Receipt key={card.id} action={action} onView={setViewing} />;
        const reason = action.status === "refused" ? action.reasons[0]?.title[language ?? "en"] : undefined;
        return (
          <p key={card.id} className="rounded-card border border-line bg-surface px-4 py-2 text-13 text-body">
            <span className="font-medium text-ink">{CLOSED_LABELS[action.status]}: </span>
            {card.summary}
            {reason && ` · ${reason}`}
          </p>
        );
      })}
    </>
  );
}
