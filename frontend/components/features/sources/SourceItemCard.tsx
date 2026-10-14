"use client";

import { BadgeCheck, Check, CircleX, ExternalLink, Pencil, RefreshCw, TriangleAlert, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Language, SourceItem, SourceItemEdit, SourceItemStatus, SourceVocabulary } from "@/lib/types";

export const ITEM_STATUS: Record<SourceItemStatus, { label: string; tone: BadgeTone; icon: typeof Check }> = {
  proposed: { label: "To review", tone: "warning", icon: TriangleAlert },
  needs_review: { label: "Re-review", tone: "warning", icon: RefreshCw },
  approved: { label: "Approved", tone: "success", icon: BadgeCheck },
  rejected: { label: "Rejected", tone: "neutral", icon: CircleX },
};

const FIELD = "h-10 w-full rounded-control border border-line bg-surface px-3 text-15 text-ink";

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Try again.";
}

/** Who decided, and when; or who proposed it, for an item still waiting. */
function provenance(item: SourceItem): string {
  if (item.reviewer && item.reviewed_at) {
    const verb = item.status === "rejected" ? "Rejected" : "Approved";
    return `${verb} by ${item.reviewer} · ${formatDate(item.reviewed_at.slice(0, 10))}`;
  }
  const sure = item.confidence === null ? "" : ` · ${Math.round(item.confidence * 100)}% sure`;
  return item.model ? `Proposed by ${item.model}${sure}` : "Written by people";
}

function EditForm({
  item,
  vocabulary,
  onSaved,
  onCancel,
}: {
  item: SourceItem;
  vocabulary: SourceVocabulary;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [institution, setInstitution] = useState(item.institution);
  const [value, setValue] = useState(item.value);
  const [description, setDescription] = useState(item.description);
  const [examples, setExamples] = useState(item.examples.join("; "));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pattern = item.predicate === "known_scam_pattern";
  const choices = pattern ? vocabulary.patterns : item.predicate === "policy" ? vocabulary.policies : null;

  async function save(event: FormEvent) {
    event.preventDefault();
    const changes: SourceItemEdit = pattern
      ? {
          value,
          description,
          examples: examples
            .split(";")
            .map((part) => part.trim())
            .filter(Boolean),
        }
      : { institution, value };
    setSaving(true);
    setError(null);
    try {
      await api.editItem(item.id, changes);
      onSaved();
    } catch (cause) {
      setError(message(cause));
      setSaving(false);
    }
  }

  const id = `edit-${item.id}`;
  return (
    <form onSubmit={save} className="mt-3 grid grid-cols-2 gap-3 rounded-control bg-paper p-3">
      {!pattern && (
        <label className="flex flex-col gap-1 text-13 text-muted">
          Institution
          <select value={institution} onChange={(event) => setInstitution(event.target.value)} className={FIELD}>
            {vocabulary.institutions.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
      )}
      <label className="flex flex-col gap-1 text-13 text-muted">
        {pattern ? "Pattern" : item.predicate === "policy" ? "Policy" : item.label}
        {choices ? (
          <select value={value} onChange={(event) => setValue(event.target.value)} className={FIELD}>
            {choices.map((choice) => (
              <option key={choice.name} value={choice.name}>
                {choice.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            id={`${id}-value`}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            className={FIELD}
          />
        )}
      </label>
      {pattern && (
        <>
          <label className="flex flex-col gap-1 text-13 text-muted">
            Description
            <input value={description} onChange={(event) => setDescription(event.target.value)} className={FIELD} />
          </label>
          <label className="col-span-2 flex flex-col gap-1 text-13 text-muted">
            Example phrases, separated by ;
            <input value={examples} onChange={(event) => setExamples(event.target.value)} className={FIELD} />
          </label>
        </>
      )}
      <div className="col-span-2 flex items-center gap-2">
        <Button type="submit" size="sm" loading={saving}>
          Save
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        {error && (
          <p role="alert" className="text-13 font-medium text-danger">
            {error}
          </p>
        )}
      </div>
    </form>
  );
}

/** One proposed fact or scam pattern: what it means, the sentence it rests on, and the decision. */
export function SourceItemCard({
  item,
  shown,
  loadVocabulary,
  onChanged,
}: {
  item: SourceItem;
  shown: Language;
  loadVocabulary: () => Promise<SourceVocabulary>;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [vocabulary, setVocabulary] = useState<SourceVocabulary | null>(null);
  const status = ITEM_STATUS[item.status];
  const waiting = item.status === "proposed" || item.status === "needs_review";

  async function decide(kind: "approve" | "reject") {
    setBusy(kind);
    setError(null);
    try {
      await (kind === "approve" ? api.approveItem(item.id) : api.rejectItem(item.id));
      onChanged();
    } catch (cause) {
      setError(message(cause));
    } finally {
      setBusy(null);
    }
  }

  async function openEdit() {
    setError(null);
    try {
      setVocabulary(await loadVocabulary());
    } catch (cause) {
      setError(message(cause));
    }
  }

  return (
    <li
      className="rounded-card border border-line bg-surface p-4 motion-safe:animate-step-in"
      aria-label={`${item.label}: ${item.words.en}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-13 text-muted">{item.label}</p>
          <p lang={shown} className="text-15 font-medium text-ink">
            {item.words[shown]}
          </p>
        </div>
        <Badge tone={status.tone} icon={status.icon}>
          {status.label}
        </Badge>
      </div>

      <blockquote className="mt-3 border-l-2 border-amber-line pl-3 text-13 text-body">
        <mark className="rounded-sm bg-amber-tint px-0.5 text-ink">“{item.sentence}”</mark>
        {item.link && (
          <a
            href={item.link}
            target="_blank"
            rel="noreferrer"
            className="ml-2 inline-flex items-center gap-1 rounded-sm font-medium whitespace-nowrap text-teal underline-offset-2 hover:underline"
          >
            <ExternalLink aria-hidden className="size-3.5" />
            Open source
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        )}
      </blockquote>
      {item.status === "needs_review" && (
        <p className="mt-2 text-13 text-amber-ink">The page changed since this was approved.</p>
      )}

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {waiting && (
            <>
              <Button
                size="sm"
                icon={Check}
                loading={busy === "approve"}
                disabled={busy !== null}
                onClick={() => decide("approve")}
              >
                Approve
              </Button>
              <Button
                variant="secondary"
                size="sm"
                icon={X}
                loading={busy === "reject"}
                disabled={busy !== null}
                onClick={() => decide("reject")}
              >
                Reject
              </Button>
            </>
          )}
          {item.status !== "rejected" && !vocabulary && (
            <Button
              variant="ghost"
              size="sm"
              icon={Pencil}
              disabled={busy !== null}
              onClick={openEdit}
              className={waiting ? undefined : "-ml-3"}
            >
              Edit
            </Button>
          )}
        </div>
        <span className="text-13 text-muted">
          {provenance(item)}
          {item.edited ? " · Edited" : ""}
        </span>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-13 font-medium text-danger">
          {error}
        </p>
      )}
      {vocabulary && (
        <EditForm
          item={item}
          vocabulary={vocabulary}
          onCancel={() => setVocabulary(null)}
          onSaved={() => {
            setVocabulary(null);
            onChanged();
          }}
        />
      )}
    </li>
  );
}
