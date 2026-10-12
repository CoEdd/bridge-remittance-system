"use client";

import { ArrowRight, CircleCheck, Hourglass } from "lucide-react";
import Link from "next/link";
import { describeAction, isWaiting } from "@/components/features/assistant/model";
import { Rows, tierOf } from "@/components/features/assistant/StepCard";
import type { Row } from "@/components/features/assistant/details";
import { Badge, TierBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { formatAmount, formatTimestampUtc } from "@/lib/format";
import { useLanguage } from "@/lib/language";
import type { Action, ApprovalEvent } from "@/lib/types";

const CLOSED_LABELS: Partial<Record<Action["status"], string>> = {
  cancelled: "Cancelled",
  expired: "Expired",
  refused: "Refused",
};

function receiptRows(action: Action): Row[] {
  const cost = action.cost_breakdown;
  const rows: Row[] = [];
  if (cost?.kind === "payment") {
    rows.push(["Amount", formatAmount(cost.amount_minor, cost.currency)], ["Payee", cost.payee_name]);
  }
  if (cost?.kind === "conversion") {
    rows.push(
      ["Converted", formatAmount(cost.amount_minor, cost.from_currency)],
      ["Received", formatAmount(cost.amount_received_minor, cost.to_currency)],
      ["Fee", formatAmount(cost.fee_minor, cost.from_currency)],
    );
  }
  if (action.executed_posting_id !== null) rows.push(["Posting", `#${action.executed_posting_id}`]);
  if (action.closed_at) rows.push(["Time", formatTimestampUtc(action.closed_at)]);
  return rows;
}

/** Proof that an approved action ran: what moved, the ledger posting, and its audit entry. */
function Receipt({ action }: { action: Action }) {
  return (
    <section
      aria-label="Receipt"
      className="rounded-card border border-teal bg-surface p-4 motion-safe:animate-step-in"
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-15 font-semibold text-ink">
          <CircleCheck aria-hidden className="size-5 shrink-0 text-teal" />
          {describeAction(action)}
        </h3>
        <Badge tone="success">{action.cost_breakdown?.kind === "conversion" ? "Converted" : "Paid"}</Badge>
      </div>
      <Rows rows={receiptRows(action)} />
      {action.audit_seq !== null && (
        <Link
          href={`/audit?entry=${action.audit_seq}`}
          className="mt-3 inline-flex items-center gap-1 rounded-sm text-13 font-medium text-teal hover:underline"
        >
          View in audit log
          <ArrowRight aria-hidden className="size-4" />
        </Link>
      )}
    </section>
  );
}

interface PlanBlockProps {
  approval: ApprovalEvent;
  /** The current state of every action, from the backend. */
  actions: Action[];
  onOpen: (planId: string) => void;
}

/** The plan a turn proposed: what still waits for the student, and a receipt for each step that ran. */
export function PlanBlock({ approval, actions, onOpen }: PlanBlockProps) {
  const { language } = useLanguage();
  const plan = approval.actions.map((card) => ({ card, action: actions.find((item) => item.id === card.id) }));
  const waiting = plan.filter(({ action }) => !action || isWaiting(action));

  return (
    <>
      {plan.map(({ card, action }) => {
        if (!action || isWaiting(action)) return null;
        if (action.status === "executed") return <Receipt key={card.id} action={action} />;
        const reason = action.status === "refused" ? action.reasons[0]?.title[language ?? "en"] : undefined;
        return (
          <p key={card.id} className="rounded-card border border-line bg-surface px-4 py-2 text-13 text-body">
            <span className="font-medium text-ink">{CLOSED_LABELS[action.status]}: </span>
            {card.summary}
            {reason && ` · ${reason}`}
          </p>
        );
      })}
      {waiting.length > 0 && (
        <section
          aria-label="Waiting for your approval"
          className="rounded-card border border-amber-line bg-amber-tint p-4 motion-safe:animate-step-in"
        >
          <h3 className="flex items-center gap-2 text-15 font-semibold text-amber-ink">
            <Hourglass aria-hidden className="size-5" />
            Waiting for your approval
          </h3>
          <ol className="mt-2 flex flex-col gap-2">
            {waiting.map(({ card }) => (
              <li key={card.id} className="flex items-center justify-between gap-3">
                <span className="text-15 text-ink">{card.summary}</span>
                <TierBadge tier={tierOf(card.tier)} />
              </li>
            ))}
          </ol>
          <Button className="mt-3" onClick={() => onOpen(approval.plan_id)}>
            Review and approve
          </Button>
        </section>
      )}
    </>
  );
}
