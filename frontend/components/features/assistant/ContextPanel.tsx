import { ArrowDownLeft } from "lucide-react";
import type { ReactNode } from "react";
import type { Live } from "@/components/features/assistant/useAssistant";
import { Amount } from "@/components/ui/Amount";
import { AnimatedAmount } from "@/components/ui/AnimatedAmount";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type { Bill } from "@/lib/types";

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

/** The two facts behind the conversation, kept up to date: the bill in question and the wallets. */
export function ContextPanel({ live }: { live: Live }) {
  const { accounts, actions, bills, documents, received } = live;
  const bill = bills.find((item) => item.document_id === documents[0]?.id) ?? null;
  const blocked = actions.some(
    (action) => action.tool === "pay_bill" && action.args.bill_id === bill?.id && action.status === "refused",
  );

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
                <Badge tone={billBadge(bill, blocked).tone}>{billBadge(bill, blocked).label}</Badge>
              </div>
              {bill.status === "open" && <p className="mt-1 text-13 text-muted">{dueText(bill.due_in_days)}</p>}
            </>
          ) : (
            <p className="text-15 text-body">No bill yet.</p>
          )}
        </Section>

        <Section title="Wallets">
          <ul data-demo="wallets" className="flex flex-col gap-1 rounded-sm">
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
      </div>
    </aside>
  );
}
