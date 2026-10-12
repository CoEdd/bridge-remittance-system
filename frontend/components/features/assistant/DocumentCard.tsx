import { ArrowRight, FileText } from "lucide-react";
import Link from "next/link";
import { KIND_LABELS, STATUS, languageList } from "@/components/features/documents/labels";
import { Badge } from "@/components/ui/Badge";
import type { DocumentKind, DocumentStatus, Language, StepEvent } from "@/lib/types";

/** The document the agent just read: what it is, how much of it checked out, and a way to see the source. */
export function DocumentCard({ step }: { step: StepEvent }) {
  const details = step.details;
  if (typeof details.document_id !== "number") return null;

  const status = STATUS[details.status as DocumentStatus];
  const verified = Object.keys((details.verified_fields as object | null) ?? {}).length;
  const total = verified + (Array.isArray(details.unverified_fields) ? details.unverified_fields.length : 0);
  const languages = Array.isArray(details.languages) ? (details.languages as Language[]) : [];

  return (
    <div className="rounded-card border border-line bg-surface p-4 motion-safe:animate-step-in">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <FileText aria-hidden className="mt-0.5 size-5 shrink-0 text-muted" strokeWidth={1.75} />
          <div className="min-w-0">
            <p className="text-15 font-medium break-words text-ink">{String(details.filename)}</p>
            <p className="text-13 text-muted">
              {KIND_LABELS[details.kind as DocumentKind]} · {languageList(languages)} · {verified} of {total} fields
              verified
            </p>
          </div>
        </div>
        {status && <Badge tone={status.tone}>{status.label}</Badge>}
      </div>
      <Link
        href={`/documents?id=${details.document_id}`}
        className="mt-3 inline-flex items-center gap-1 rounded-sm text-13 font-medium text-teal hover:underline"
      >
        Open source view
        <ArrowRight aria-hidden className="size-4" />
      </Link>
    </div>
  );
}
