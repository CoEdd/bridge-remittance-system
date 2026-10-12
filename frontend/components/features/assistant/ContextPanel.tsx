import { ArrowDownLeft, ArrowRight, Ban } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import { describeAction, isWaiting } from "@/components/features/assistant/model";
import { tierOf } from "@/components/features/assistant/StepCard";
import type { Live } from "@/components/features/assistant/useAssistant";
import { Amount } from "@/components/ui/Amount";
import { AnimatedAmount } from "@/components/ui/AnimatedAmount";
import { Badge, TierBadge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import type { Action, Bill, Language } from "@/lib/types";

const STATUS_LABELS: Record<Action["status"], { label: string; tone: BadgeTone }> = {
  awaiting_confirm: { label: "Waiting", tone: "warning" },
  awaiting_otp: { label: "Needs code", tone: "warning" },
  cooling_off: { label: "Cooling off", tone: "warning" },
  executed: { label: "Done", tone: "success" },
  refused: { label: "Refused", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  expired: { label: "Expired", tone: "neutral" },
};

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-t border-line px-4 py-4 first:border-t-0">
      <h3 className="mb-2 text-13 font-medium text-muted">{title}</h3>
      {children}
    </section>
  );
}

function dueText(days: number | null): string {
  if (days === null) return "No due date";
  if (days < 0) return `Overdue by ${-days} ${days === -1 ? "day" : "days"}`;
  return days === 0 ? "Due today" : `Due in ${days} ${days === 1 ? "day" : "days"}`;
}

function billBadge(bill: Bill, blocked: boolean): { label: string; tone: BadgeTone } {
  if (bill.status === "paid") return { label: "Paid", tone: "success" };
  if (blocked) return { label: "Blocked", tone: "danger" };
  if (bill.flagged) return { label: "Risk found", tone: "warning" };
  return { label: bill.status === "open" ? "Open" : "Cancelled", tone: "neutral" };
}

interface ContextPanelProps {
  live: Live;
  language: Language;
  onOpenPlan: (planId: string) => void;
}

/** The facts behind the conversation, kept up to date: the bill, the wallets, the plan and the last block. */
export function ContextPanel({ live, language, onOpenPlan }: ContextPanelProps) {
  const { accounts, actions, bills, documents, received } = live;
  const bill = bills.find((item) => item.document_id === documents[0]?.id) ?? null;
  const blockedActions = actions.filter((action) => action.status === "refused");
  const lastBlocked = blockedActions[blockedActions.length - 1] ?? null;
  const billBlocked = blockedActions.some((action) => action.tool === "pay_bill" && action.args.bill_id === bill?.id);

  // The newest plan the agent proposed that was not refused outright.
  const planned = actions.filter((action) => action.plan_id !== null && action.tier !== "REFUSED");
  const planId = planned[planned.length - 1]?.plan_id ?? null;
  const plan = planned.filter((action) => action.plan_id === planId);

  return (
    <aside aria-labelledby="context-title" className="flex min-h-0 flex-col">
      <h2 id="context-title" className="mb-3 font-heading text-18 font-semibold text-ink">
        Context
      </h2>
      <div className="min-h-0 overflow-y-auto rounded-card border border-line bg-surface">
        <Section title="Bill">
          {bill ? (
            <>
              <p className="text-15 font-medium text-ink">{bill.payee_name}</p>
              <div className="mt-1 flex items-center justify-between gap-3">
                <Amount minor={bill.amount_minor} currency={bill.currency} className="text-18 font-semibold text-ink" />
                <Badge tone={billBadge(bill, billBlocked).tone}>{billBadge(bill, billBlocked).label}</Badge>
              </div>
              {bill.status === "open" && <p className="mt-1 text-13 text-muted">{dueText(bill.due_in_days)}</p>}
            </>
          ) : (
            <p className="text-15 text-body">No bill yet.</p>
          )}
        </Section>

        <Section title="Wallets">
          <ul className="flex flex-col gap-1">
            {accounts.accounts.map((account) => (
              <li key={account.id} className="flex items-baseline justify-between gap-3">
                <span className="text-15 text-body">{account.currency}</span>
                <AnimatedAmount
                  minor={account.balance_minor}
                  currency={account.currency}
                  className="text-18 font-semibold text-ink"
                />
              </li>
            ))}
          </ul>
          {received?.amounts[0] && (
            <p className="mt-2 flex items-start gap-2 text-13 text-body">
              <ArrowDownLeft aria-hidden className="mt-0.5 size-4 shrink-0 text-teal" />
              <span>
                Received <Amount minor={received.amounts[0].amount_minor} currency={received.amounts[0].currency} /> from{" "}
                {received.counterparty ?? "an unknown sender"}
              </span>
            </p>
          )}
        </Section>

        <Section title="Plan">
          {plan.length === 0 ? (
            <p className="text-15 text-body">No plan yet.</p>
          ) : (
            <>
              <ol className="flex flex-col gap-3">
                {plan.map((action, index) => (
                  <li key={action.id} className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1">
                    <span className="text-15 font-medium text-muted">{index + 1}.</span>
                    <span className="text-15 text-ink">{describeAction(action)}</span>
                    <span className="col-start-2 flex items-center gap-2">
                      <TierBadge tier={tierOf(action.tier)} />
                      <Badge tone={STATUS_LABELS[action.status].tone}>{STATUS_LABELS[action.status].label}</Badge>
                    </span>
                  </li>
                ))}
              </ol>
              {planId && plan.some(isWaiting) && (
                <Button size="sm" className="mt-3" onClick={() => onOpenPlan(planId)}>
                  Open
                </Button>
              )}
            </>
          )}
        </Section>

        {lastBlocked && (
          <Section title="Blocked">
            <p className="flex items-start gap-2 text-15 text-ink">
              <Ban aria-hidden className="mt-0.5 size-4 shrink-0 text-danger" />
              {describeAction(lastBlocked)}
            </p>
            <p lang={language} className="mt-1 text-13 text-body">
              {lastBlocked.reasons.map((reason) => reason.title[language]).join(" · ")}
            </p>
            {lastBlocked.audit_seq !== null && (
              <Link
                href={`/audit?entry=${lastBlocked.audit_seq}`}
                className="mt-2 inline-flex items-center gap-1 rounded-sm text-13 font-medium text-teal hover:underline"
              >
                View in audit log
                <ArrowRight aria-hidden className="size-4" />
              </Link>
            )}
          </Section>
        )}
      </div>
    </aside>
  );
}
