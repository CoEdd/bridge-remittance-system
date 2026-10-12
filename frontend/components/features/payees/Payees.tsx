"use client";

import { ArrowRight, BadgeCheck, Eye, EyeOff, TriangleAlert, Users } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { Loadable } from "@/components/features/home/Loadable";
import { Amount } from "@/components/ui/Amount";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { formatDate, formatTimestampUtc } from "@/lib/format";
import type { Bill, Payee } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const SOURCES: Record<NonNullable<Payee["verified_source"]>, string> = {
  institution_registry: "University registry",
  past_payment: "Past payment",
  manual: "Manual",
};

/** "4100 2026 0000 8815" -> "•••• •••• •••• 8815": every digit but the last four is hidden. */
function masked(account: string): string {
  let digitsLeft = account.replace(/\D/g, "").length;
  return account.replace(/\d/g, (digit) => {
    digitsLeft -= 1;
    return digitsLeft < 4 ? digit : "•";
  });
}

function billBadge(bill: Bill): { label: string; tone: BadgeTone } {
  if (bill.status === "paid") return { label: "Paid", tone: "success" };
  if (bill.flagged) return { label: "Risk found", tone: "warning" };
  return { label: bill.status === "open" ? "Open" : "Cancelled", tone: "neutral" };
}

function PayeeRow({ payee, bills }: { payee: Payee; bills: Bill[] }) {
  const [shown, setShown] = useState(false);
  return (
    <tr className="border-b border-line align-top last:border-b-0">
      <th scope="row" className="py-3 pr-4 text-15 font-medium text-ink">
        {payee.name}
      </th>
      <td className="py-3 pr-4 text-15 text-body">{payee.bank_name}</td>
      <td className="py-3 pr-4">
        <span className="block font-heading text-15 whitespace-nowrap text-ink tabular-nums">
          {shown ? payee.account_ref : masked(payee.account_ref)}
        </span>
        <Button
          variant="ghost"
          size="sm"
          icon={shown ? EyeOff : Eye}
          aria-pressed={shown}
          aria-label={`${shown ? "Hide" : "Show"} the account number of ${payee.name}`}
          className="-ml-3"
          onClick={() => setShown(!shown)}
        >
          {shown ? "Hide" : "Show"}
        </Button>
      </td>
      <td className="py-3 pr-4">
        {payee.verified_source ? (
          <Badge tone="success" icon={BadgeCheck}>
            {SOURCES[payee.verified_source]}
          </Badge>
        ) : (
          <Badge tone="warning" icon={TriangleAlert}>
            Not verified
          </Badge>
        )}
      </td>
      <td className="py-3 pr-4 text-15 whitespace-nowrap text-body">
        {payee.first_paid_at ? formatDate(payee.first_paid_at) : "Never"}
      </td>
      <td className="py-3 pr-4 text-15 text-body">
        {payee.cooling_off_until ? (
          <>
            <Badge tone="warning">Cooling off</Badge>
            <span className="mt-1 block text-13 text-muted">Until {formatTimestampUtc(payee.cooling_off_until)}</span>
          </>
        ) : (
          "None"
        )}
      </td>
      <td className="py-3">
        {bills.length === 0 ? (
          <span className="text-15 text-body">None</span>
        ) : (
          <ul className="flex flex-col gap-1">
            {bills.map((bill) => (
              <li key={bill.id} className="flex items-center justify-between gap-3">
                <Amount minor={bill.amount_minor} currency={bill.currency} className="text-15 text-ink" />
                <Badge tone={billBadge(bill).tone}>{billBadge(bill).label}</Badge>
              </li>
            ))}
          </ul>
        )}
      </td>
    </tr>
  );
}

/** Everyone the student has paid, or that a document asked them to pay, with how far each one is verified. */
export function Payees() {
  const load = useCallback((signal: AbortSignal) => Promise.all([api.payees(signal), api.bills(signal)]), []);
  const result = useApi(load);

  return (
    <Card>
      <Loadable
        result={result}
        loadingLabel="Loading payees"
        loading={
          <div className="flex flex-col gap-3">
            {[0, 1, 2].map((key) => (
              <Skeleton key={key} className="h-14 w-full" />
            ))}
          </div>
        }
      >
        {([payees, bills]) =>
          payees.length === 0 ? (
            <EmptyState
              icon={Users}
              message="There are no payees yet."
              action={
                <Link href="/documents" className={buttonClasses("secondary")}>
                  Open Documents
                  <ArrowRight aria-hidden className="size-4" />
                </Link>
              }
            />
          ) : (
            <table className="w-full text-left">
              <caption className="sr-only">Payees and how each one is verified</caption>
              <thead>
                <tr className="border-b border-line text-13 text-muted">
                  {["Payee", "Bank", "Account", "Verification", "First paid", "Cooling-off", "Bills"].map((heading) => (
                    <th key={heading} scope="col" className="pr-4 pb-2 font-medium last:pr-0">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {payees.map((payee) => (
                  <PayeeRow key={payee.id} payee={payee} bills={bills.filter((bill) => bill.payee_id === payee.id)} />
                ))}
              </tbody>
            </table>
          )
        }
      </Loadable>
    </Card>
  );
}
