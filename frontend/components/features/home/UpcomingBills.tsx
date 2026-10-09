"use client";

import { ArrowRight, Receipt } from "lucide-react";
import Link from "next/link";
import { Loadable } from "@/components/features/home/Loadable";
import { Amount } from "@/components/ui/Amount";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

/** "Due in N days", counted by the backend from the demo date. */
function dueLabel(days: number): { text: string; tone: BadgeTone } {
  if (days < 0) {
    const late = Math.abs(days);
    return { text: `Overdue by ${late} ${late === 1 ? "day" : "days"}`, tone: "danger" };
  }
  if (days === 0) return { text: "Due today", tone: "warning" };
  return {
    text: `Due in ${days} ${days === 1 ? "day" : "days"}`,
    tone: days <= 7 ? "warning" : "neutral",
  };
}

export function UpcomingBills() {
  const result = useApi(api.bills);

  return (
    <Card title="Upcoming bills">
      <Loadable
        result={result}
        loadingLabel="Loading bills"
        loading={
          <div className="flex flex-col gap-4">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        }
      >
        {(bills) => {
          // Bills from untrusted or risky documents, and requests with no date, are not listed here.
          const open = bills.filter((bill) => bill.status === "open" && !bill.flagged && bill.due_date !== null);
          if (open.length === 0) {
            return (
              <EmptyState
                icon={Receipt}
                message="There are no upcoming bills."
                action={
                  <Link href="/documents" className={buttonClasses("secondary")}>
                    Open Documents
                    <ArrowRight aria-hidden className="size-4" />
                  </Link>
                }
              />
            );
          }
          return (
            <ul className="flex flex-col">
              {open.map((bill) => {
                const due = dueLabel(bill.due_in_days ?? 0);
                return (
                  <li
                    key={bill.id}
                    className="flex items-center justify-between gap-4 border-t border-line py-4 first:border-t-0 first:pt-0 last:pb-0"
                  >
                    <div>
                      <p className="text-15 font-medium text-ink">{bill.payee_name}</p>
                      <p className="text-13 text-muted">Due {formatDate(bill.due_date ?? "")}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <Amount
                        minor={bill.amount_minor}
                        currency={bill.currency}
                        className="text-18 font-semibold text-ink"
                      />
                      <Badge tone={due.tone}>{due.text}</Badge>
                    </div>
                  </li>
                );
              })}
            </ul>
          );
        }}
      </Loadable>
    </Card>
  );
}
