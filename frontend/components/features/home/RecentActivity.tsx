"use client";

import { ArrowRight, ReceiptText } from "lucide-react";
import Link from "next/link";
import { Loadable } from "@/components/features/home/Loadable";
import { Amount } from "@/components/ui/Amount";
import { Badge } from "@/components/ui/Badge";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const RECENT_COUNT = 8;

function loadRecent(signal: AbortSignal) {
  return api.transactions({ limit: RECENT_COUNT }, signal);
}

export function RecentActivity() {
  const result = useApi(loadRecent);

  return (
    <Card title="Recent activity">
      <Loadable
        result={result}
        loadingLabel="Loading recent activity"
        loading={
          <div className="flex flex-col gap-3">
            {[0, 1, 2, 3].map((key) => (
              <Skeleton key={key} className="h-8 w-full" />
            ))}
          </div>
        }
      >
        {(transactions) =>
          transactions.length === 0 ? (
            <EmptyState
              icon={ReceiptText}
              message="There is no activity yet."
              action={
                <Link href="/assistant" className={buttonClasses("secondary")}>
                  Open Assistant
                  <ArrowRight aria-hidden className="size-4" />
                </Link>
              }
            />
          ) : (
            <table className="w-full text-left">
              <caption className="sr-only">The last {RECENT_COUNT} transactions</caption>
              <thead>
                <tr className="border-b border-line text-13 text-muted">
                  <th scope="col" className="w-32 pb-2 font-medium">
                    Date
                  </th>
                  <th scope="col" className="pb-2 font-medium">
                    Description
                  </th>
                  <th scope="col" className="w-40 pb-2 font-medium">
                    Category
                  </th>
                  <th scope="col" className="w-40 pb-2 text-right font-medium">
                    Amount
                  </th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((transaction) => (
                  <tr key={transaction.id} className="border-b border-line last:border-b-0">
                    <td className="py-3 text-13 text-muted">{formatDate(transaction.business_date)}</td>
                    <td className="py-3">
                      <span className="text-15 text-ink">
                        {transaction.counterparty ?? transaction.description}
                      </span>
                      {transaction.counterparty && (
                        <span className="ml-2 text-13 text-muted">{transaction.description}</span>
                      )}
                    </td>
                    <td className="py-3">
                      <Badge>{transaction.category_label}</Badge>
                    </td>
                    <td className="py-3 text-right">
                      {transaction.amounts.map((amount) => (
                        <Amount
                          key={amount.currency}
                          minor={amount.amount_minor}
                          currency={amount.currency}
                          className="block text-15 font-medium text-ink"
                        />
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        }
      </Loadable>
    </Card>
  );
}
