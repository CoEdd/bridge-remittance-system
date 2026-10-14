"use client";

import clsx from "clsx";
import { BookCheck, ExternalLink, Plus, RefreshCw, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Loadable } from "@/components/features/home/Loadable";
import { SourceItemCard } from "@/components/features/sources/SourceItemCard";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useLanguage } from "@/lib/language";
import type {
  RuleSource,
  RuleSourceDetail,
  RuleSources as RuleSourcesData,
  SourceItemStatus,
  SourceVocabulary,
} from "@/lib/types";
import { useApi } from "@/lib/useApi";

// Items waiting for a person come first.
const ORDER: Record<SourceItemStatus, number> = {
  proposed: 0,
  needs_review: 0,
  approved: 1,
  rejected: 2,
};

function waiting(source: RuleSource): number {
  return source.counts.proposed + source.counts.needs_review;
}

function where(source: RuleSource): string {
  if (source.kind === "bundled") return source.domain ? `${source.domain} · bundled sample` : "Bundled sample";
  if (source.kind === "upload") return "Uploaded PDF";
  return source.domain ?? "Web page";
}

/** Add a page by its address, or upload a PDF. Live mode only: Claude reads it. */
function AddSource({ data, onAdded }: { data: RuleSourcesData; onAdded: (source: RuleSourceDetail) => void }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const disabled = !data.can_add || busy;

  async function run(work: () => Promise<RuleSourceDetail>) {
    setBusy(true);
    setError(null);
    try {
      const added = await work();
      setUrl("");
      onAdded(added);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (url.trim()) void run(() => api.addSource(url.trim()));
  }

  return (
    <Card>
      <form onSubmit={submit} className="flex items-center gap-3">
        <label htmlFor="source-url" className="sr-only">
          Page address
        </label>
        <input
          id="source-url"
          type="url"
          required
          value={url}
          disabled={disabled}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://… a university or government page about fees or scams"
          className="h-10 min-w-0 flex-1 rounded-control border border-line bg-surface px-3 text-15 text-ink disabled:bg-paper disabled:text-muted"
        />
        <Button type="submit" variant="secondary" icon={Plus} loading={busy} disabled={disabled}>
          Add page
        </Button>
        <Button variant="ghost" icon={Upload} disabled={disabled} onClick={() => fileInput.current?.click()}>
          Upload PDF
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void run(() => api.uploadSource(file));
          }}
        />
      </form>
      <div aria-live="polite">
        {busy && (
          <p className="mt-2 text-13 text-muted">Reading the page and proposing items. This takes about 20 seconds.</p>
        )}
        {!data.can_add && data.note && <p className="mt-2 text-13 text-muted">{data.note}</p>}
        {error && (
          <p role="alert" className="mt-2 text-13 font-medium text-danger">
            {error}
          </p>
        )}
      </div>
    </Card>
  );
}

function SourceList({
  sources,
  selected,
  onSelect,
}: {
  sources: RuleSource[];
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <nav aria-label="Sources">
      <ul className="flex flex-col gap-2">
        {sources.map((source) => (
          <li key={source.id}>
            <button
              type="button"
              aria-current={source.id === selected ? "true" : undefined}
              onClick={() => onSelect(source.id)}
              className={clsx(
                "flex w-full flex-col gap-1 rounded-card border p-3 text-left transition-colors duration-150",
                source.id === selected ? "border-teal bg-teal-tint" : "border-line bg-surface hover:border-muted",
              )}
            >
              <span className="truncate text-15 font-medium text-ink">{source.title}</span>
              <span className="text-13 text-muted">{where(source)}</span>
              <span className="flex flex-wrap gap-1">
                {waiting(source) > 0 && <Badge tone="warning">{waiting(source)} to review</Badge>}
                {source.counts.approved > 0 && <Badge tone="success">{source.counts.approved} approved</Badge>}
                {source.counts.rejected > 0 && <Badge>{source.counts.rejected} rejected</Badge>}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function SourceDetail({ id, version, onChanged }: { id: number; version: number; onChanged: () => void }) {
  const { language } = useLanguage();
  const [detail, setDetail] = useState<RuleSourceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const vocabulary = useRef<Promise<SourceVocabulary> | null>(null);

  const load = useCallback(() => {
    api.ruleSource(id).then(
      (data) => {
        setDetail(data);
        setError(null);
      },
      (cause: unknown) => setError(cause instanceof ApiError ? cause.message : "The source could not be loaded."),
    );
  }, [id]);
  useEffect(load, [load, version]);

  const loadVocabulary = useCallback(() => {
    vocabulary.current ??= api.sourceVocabulary();
    return vocabulary.current;
  }, []);

  async function checkAgain() {
    setChecking(true);
    try {
      setDetail(await api.refetchSource(id));
      onChanged();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "The page could not be fetched.");
    } finally {
      setChecking(false);
    }
  }

  if (error && !detail) return <ErrorState message={error} onRetry={load} />;
  if (!detail || detail.id !== id) {
    return (
      <div role="status" className="flex flex-col gap-3">
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-32 w-full" />
        <span className="sr-only">Loading the source</span>
      </div>
    );
  }
  const items = [...detail.items].sort((a, b) => ORDER[a.status] - ORDER[b.status] || a.id - b.id);

  return (
    <section aria-labelledby="source-title" className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 id="source-title" className="font-heading text-24 font-semibold text-ink">
            {detail.title}
          </h2>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 text-13 text-muted">
            <span>{where(detail)}</span>
            <span>Fetched {formatDate(detail.fetched_at.slice(0, 10))}</span>
            {detail.url && (
              <a
                href={detail.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-sm font-medium text-teal underline-offset-2 hover:underline"
              >
                <ExternalLink aria-hidden className="size-3.5" />
                Open page
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            )}
          </p>
          {detail.dropped > 0 && (
            <p className="mt-1 text-13 text-muted">
              {detail.dropped} {detail.dropped === 1 ? "proposal was" : "proposals were"} dropped by the checks.
            </p>
          )}
        </div>
        {detail.kind === "url" && (
          <Button variant="ghost" size="sm" icon={RefreshCw} loading={checking} onClick={checkAgain}>
            Check again
          </Button>
        )}
      </div>
      {error && (
        <p role="alert" className="text-13 font-medium text-danger">
          {error}
        </p>
      )}
      {items.length === 0 ? (
        <p className="text-15 text-body">Nothing on this page fits the rule vocabulary.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((item) => (
            <SourceItemCard
              key={`${item.id}-${item.status}-${item.value}`}
              item={item}
              shown={language ?? "en"}
              loadVocabulary={loadVocabulary}
              onChanged={() => {
                load();
                onChanged();
              }}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

/** Where institution facts and scam patterns come from, and the person who approved each one. */
export function RuleSources() {
  const result = useApi(api.ruleSources);
  const [selected, setSelected] = useState<number | null>(null);
  const [version, setVersion] = useState(0);
  // Counts after a decision, fetched quietly so the page does not flash back to loading.
  const [fresh, setFresh] = useState<RuleSourcesData | null>(null);
  const refresh = useCallback(() => {
    api.ruleSources().then(setFresh, () => undefined);
  }, []);
  const { state } = result;

  // Open the first source with something to review, or the first one.
  const sources = fresh?.sources ?? (state.status === "ready" ? state.data.sources : []);
  const chosen = selected ?? (sources.find((source) => waiting(source) > 0) ?? sources[0])?.id ?? null;

  return (
    <Loadable
      result={result}
      loadingLabel="Loading rule sources"
      loading={
        <div className="flex flex-col gap-6">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      }
    >
      {(loaded) => {
        const data = fresh ?? loaded;
        return (
          <div className="flex flex-col gap-6">
            <AddSource
              data={data}
              onAdded={(added) => {
                setSelected(added.id);
                refresh();
              }}
            />
            {data.sources.length === 0 ? (
              <Card>
                <EmptyState
                  icon={BookCheck}
                  message="There are no rule sources yet."
                  action={<span className="text-13 text-muted">Add a page above.</span>}
                />
              </Card>
            ) : (
              <div className="grid grid-cols-[300px_minmax(0,1fr)] items-start gap-6">
                <SourceList sources={data.sources} selected={chosen} onSelect={setSelected} />
                <Card>
                  {chosen !== null && (
                    <SourceDetail
                      id={chosen}
                      version={version}
                      onChanged={() => {
                        setVersion((value) => value + 1);
                        refresh();
                      }}
                    />
                  )}
                </Card>
              </div>
            )}
          </div>
        );
      }}
    </Loadable>
  );
}
