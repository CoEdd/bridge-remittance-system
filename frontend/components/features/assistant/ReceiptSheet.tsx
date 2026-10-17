"use client";

import { BadgeCheck, Download } from "lucide-react";
import { useCallback } from "react";
import { Loadable } from "@/components/features/home/Loadable";
import { Badge } from "@/components/ui/Badge";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { formatAmount, formatDate } from "@/lib/format";
import type { Receipt } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const SAMPLE_FOOTER = "Sample document · fictional institution · created for a sandbox demo";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-3 border-b border-line py-3 last:border-b-0">
      <dt className="text-13 text-muted">{label}</dt>
      <dd className="text-15 break-words text-ink">{children}</dd>
    </div>
  );
}

function ReceiptBody({ receipt }: { receipt: Receipt }) {
  return (
    <div className="rounded-card border border-line bg-surface p-6">
      <div className="flex items-start justify-between gap-4 border-b-2 border-ink pb-4">
        <div>
          <p className="font-heading text-24 font-semibold text-ink">Payment receipt</p>
          <p className="text-13 text-muted">Bridge</p>
        </div>
        <p className="text-13 text-muted tabular-nums">{receipt.receipt_number}</p>
      </div>
      <div className="flex items-end justify-between gap-4 py-6">
        <div>
          <p className="text-13 text-muted">Amount paid</p>
          <p className="font-heading text-32 font-semibold text-ink tabular-nums">
            {formatAmount(receipt.amount_minor, receipt.currency)}
          </p>
        </div>
        <Badge tone="success" icon={BadgeCheck}>
          {receipt.status}
        </Badge>
      </div>
      <dl>
        <Row label="Date">{formatDate(receipt.business_date)}</Row>
        <Row label="Time">{receipt.executed_at.slice(11, 19)} UTC</Row>
        <Row label="From">{receipt.from_account}</Row>
        <Row label="Payee">{receipt.payee_name}</Row>
        <Row label="Payee account">
          <span className="tabular-nums">{receipt.payee_account}</span>
          {receipt.payee_verified && <span className="block text-13 text-muted">Verified: {receipt.payee_verified}</span>}
        </Row>
        <Row label="Reference">{receipt.reference ?? "None"}</Row>
        <Row label="Audit entry">
          #{receipt.audit_seq} <span className="text-13 text-muted">hash {receipt.audit_hash}</span>
        </Row>
      </dl>
      <p className="mt-4 text-13 text-body">No real money moved: this payment ran in the Bridge sandbox ledger.</p>
      <p className="mt-6 text-13 text-muted">{SAMPLE_FOOTER}</p>
    </div>
  );
}

/** The receipt of one executed payment, with the same receipt as a PDF to download. */
export function ReceiptSheet({ actionId, onClose }: { actionId: number | null; onClose: () => void }) {
  return (
    <Sheet
      open={actionId !== null}
      onClose={onClose}
      title="Receipt"
      width="wide"
      footer={
        actionId !== null && (
          <>
            <Button variant="secondary" onClick={onClose}>
              Close
            </Button>
            <a href={api.receiptPdfUrl(actionId)} download className={buttonClasses("primary")}>
              <Download aria-hidden className="size-4" />
              Download PDF
            </a>
          </>
        )
      }
    >
      {actionId !== null && <LoadedReceipt actionId={actionId} />}
    </Sheet>
  );
}

function LoadedReceipt({ actionId }: { actionId: number }) {
  const load = useCallback((signal: AbortSignal) => api.receipt(actionId, signal), [actionId]);
  const result = useApi(load);
  return (
    <Loadable result={result} loadingLabel="Loading the receipt" loading={<Skeleton className="h-96 w-full" />}>
      {(receipt) => <ReceiptBody receipt={receipt} />}
    </Loadable>
  );
}
