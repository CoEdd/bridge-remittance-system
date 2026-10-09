"use client";

import { ArrowRight, Wallet } from "lucide-react";
import Link from "next/link";
import { Loadable } from "@/components/features/home/Loadable";
import { Amount } from "@/components/ui/Amount";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { CategorySpend } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function changeText(change: number | null): string {
  if (change === null) return "New";
  if (change === 0) return "No change";
  return change > 0 ? `Up ${change}%` : `Down ${Math.abs(change)}%`;
}

function SpendingBar({ item, largest }: { item: CategorySpend; largest: number }) {
  // Bar length compares categories in home-currency terms; at least 1% so it stays visible.
  const width = largest > 0 ? Math.max(1, Math.round((item.home_equivalent_minor / largest) * 100)) : 0;
  return (
    <li>
      <div className="flex items-baseline justify-between gap-4">
        <span className="text-15 text-ink">{item.label}</span>
        <span className="flex items-baseline gap-4">
          <span className="text-13 text-muted">{changeText(item.change_pct)}</span>
          <Amount
            minor={item.total_minor}
            currency={item.currency}
            className="w-32 text-right text-15 font-medium text-ink"
          />
        </span>
      </div>
      <div aria-hidden className="mt-1 h-2 rounded-full bg-paper">
        <div className="h-2 rounded-full bg-teal" style={{ width: `${width}%` }} />
      </div>
    </li>
  );
}

export function SpendingCard() {
  const result = useApi(api.spending);

  return (
    <Card title="Spending, last 30 days" className="h-full">
      <Loadable
        result={result}
        loadingLabel="Loading spending"
        loading={
          <div className="flex flex-col gap-4">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        }
      >
        {(data) => {
          if (data.categories.length === 0) {
            return (
              <EmptyState
                icon={Wallet}
                message={data.insight}
                action={
                  <Link href="/assistant" className={buttonClasses("secondary")}>
                    Open Assistant
                    <ArrowRight aria-hidden className="size-4" />
                  </Link>
                }
              />
            );
          }
          const largest = Math.max(...data.categories.map((item) => item.home_equivalent_minor));
          return (
            <>
              <p className="font-heading text-18 font-semibold text-ink">{data.insight}</p>
              <p className="mt-1 text-13 text-muted">
                {formatDate(data.period_start)} to {formatDate(data.period_end)}, compared with the{" "}
                {data.period_days} days before. Bar lengths compare the amounts in {data.home_currency}.
              </p>
              <ul className="mt-6 flex flex-col gap-4">
                {data.categories.map((item) => (
                  <SpendingBar key={`${item.category}-${item.currency}`} item={item} largest={largest} />
                ))}
              </ul>
            </>
          );
        }}
      </Loadable>
    </Card>
  );
}
