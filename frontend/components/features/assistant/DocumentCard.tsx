import { ArrowRight, FileText } from "lucide-react";
import Link from "next/link";
import { STATUS } from "@/components/features/documents/labels";
import { Badge } from "@/components/ui/Badge";
import type { DocumentStatus, StepEvent } from "@/lib/types";

/** The document the agent just read, in one line: its status, how much checked out, and its source view. */
export function DocumentCard({ step }: { step: StepEvent }) {
  const details = step.details;
  if (typeof details.document_id !== "number") return null;

  const status = STATUS[details.status as DocumentStatus];
  const verified = Object.keys((details.verified_fields as object | null) ?? {}).length;
  const total = verified + (Array.isArray(details.unverified_fields) ? details.unverified_fields.length : 0);

  return (
    <div className="flex items-center gap-3 rounded-card border border-line bg-surface px-4 py-2 motion-safe:animate-step-in">
      <FileText aria-hidden className="size-5 shrink-0 text-muted" strokeWidth={1.75} />
      <span className="min-w-0 flex-1 truncate text-15 font-medium text-ink">{String(details.filename)}</span>
      <span className="text-13 whitespace-nowrap text-muted">
        {verified}/{total} verified
      </span>
      {status && <Badge tone={status.tone}>{status.label}</Badge>}
      <Link
        href={`/documents?id=${details.document_id}`}
        aria-label={`Open source view of ${String(details.filename)}`}
        className="inline-flex items-center gap-1 rounded-sm text-13 font-medium whitespace-nowrap text-teal hover:underline"
      >
        Open
        <ArrowRight aria-hidden className="size-4" />
      </Link>
    </div>
  );
}
