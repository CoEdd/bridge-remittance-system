"use client";

import { ArrowRight, FileText } from "lucide-react";
import Link from "next/link";
import { useCallback } from "react";
import { STATUS } from "@/components/features/documents/labels";
import { Badge } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { formatClock, formatTimestampUtc } from "@/lib/format";
import type { DocumentStatus, StepEvent } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function initials(name: string): string {
  const words = name.trim().split(/\s+/);
  return words.length > 1 ? `${words[0][0]}${words[words.length - 1][0]}` : name.trim().slice(0, 2);
}

/** Status, how much checked out, and the link to the source view: under a document or a message. */
function Checked({ step, documentId, filename }: { step: StepEvent; documentId: number; filename: string }) {
  const details = step.details;
  const status = STATUS[details.status as DocumentStatus];
  const verified = Object.keys((details.verified_fields as object | null) ?? {}).length;
  const total = verified + (Array.isArray(details.unverified_fields) ? details.unverified_fields.length : 0);
  return (
    <>
      <span className="text-13 whitespace-nowrap text-muted">
        {verified}/{total} verified
      </span>
      {status && <Badge tone={status.tone}>{status.label}</Badge>}
      <Link
        href={`/documents?id=${documentId}`}
        aria-label={`Open source view of ${filename}`}
        className="inline-flex items-center gap-1 rounded-sm text-13 font-medium whitespace-nowrap text-teal hover:underline"
      >
        Open
        <ArrowRight aria-hidden className="size-4" />
      </Link>
    </>
  );
}

/** A pasted or received message, shown as the chat message it was: sender, time and text. */
function MessageCard({ step, documentId, filename }: { step: StepEvent; documentId: number; filename: string }) {
  const load = useCallback((signal: AbortSignal) => api.document(documentId, signal), [documentId]);
  const { state } = useApi(load);
  if (state.status !== "ready") {
    return <Skeleton className="h-28 w-full max-w-[85%]" />;
  }
  const message = state.data;
  const sender = message.sender ?? "Unknown sender";
  return (
    <div data-demo="document" className="max-w-[85%] motion-safe:animate-step-in">
      <article
        aria-label={`Message from ${sender}`}
        className="rounded-card border border-line bg-surface px-4 py-3"
      >
        <header className="mb-2 flex items-center gap-3">
          <span
            aria-hidden
            className="flex size-8 shrink-0 items-center justify-center rounded-full bg-paper text-13 font-semibold text-body uppercase"
          >
            {initials(sender)}
          </span>
          <span className="min-w-0 flex-1 truncate text-15 font-semibold text-ink">{sender}</span>
          <time dateTime={message.created_at} title={formatTimestampUtc(message.created_at)} className="text-13 text-muted tabular-nums">
            {formatClock(message.created_at)}
          </time>
        </header>
        <p className="text-15 break-words whitespace-pre-wrap text-ink">{message.raw_text.trim()}</p>
      </article>
      <div className="mt-1 flex flex-wrap items-center gap-3 px-1">
        <Checked step={step} documentId={documentId} filename={filename} />
      </div>
    </div>
  );
}

/** The document the agent just read: one line for a file, or the message itself for a pasted or received message. */
export function DocumentCard({ step }: { step: StepEvent }) {
  const details = step.details;
  if (typeof details.document_id !== "number") return null;
  const filename = String(details.filename);

  if (details.kind === "message") {
    return <MessageCard step={step} documentId={details.document_id} filename={filename} />;
  }
  return (
    <div
      data-demo="document"
      className="flex items-center gap-3 rounded-card border border-line bg-surface px-4 py-2 motion-safe:animate-step-in"
    >
      <FileText aria-hidden className="size-5 shrink-0 text-muted" strokeWidth={1.75} />
      <span className="min-w-0 flex-1 truncate text-15 font-medium text-ink">{filename}</span>
      <Checked step={step} documentId={details.document_id} filename={filename} />
    </div>
  );
}
