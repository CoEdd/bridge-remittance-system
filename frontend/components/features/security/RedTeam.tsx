"use client";

import clsx from "clsx";
import { Check, CircleCheck, CircleX, LoaderCircle, Play, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useDemoCommands } from "@/lib/demo";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ApiError, api } from "@/lib/api";
import type { RedTeamCase, RedTeamResult, RedTeamSummary } from "@/lib/types";

function StatusBadge({ result }: { result: RedTeamResult | undefined }) {
  if (!result) return <Badge>Not run</Badge>;
  if (result.status === "running") {
    return (
      <span className="inline-flex h-6 items-center gap-1 rounded-full border border-line bg-paper px-2 text-13 font-medium text-body">
        <LoaderCircle aria-hidden className="size-3.5 motion-safe:animate-spin" />
        Running
      </span>
    );
  }
  return result.status === "passed" ? (
    <Badge tone="success" icon={CircleCheck}>
      Passed
    </Badge>
  ) : (
    <Badge tone="danger" icon={CircleX}>
      Failed
    </Badge>
  );
}

function Line({ label, text }: { label: string; text: string }) {
  return (
    <p className="text-13 text-body">
      <span className="font-medium text-ink">{label}: </span>
      {text}
    </p>
  );
}

/** One attack: its name and its result. What was tried, expected and observed opens on "Details". */
function CaseCard({ item, result }: { item: RedTeamCase; result: RedTeamResult | undefined }) {
  const finished = result && result.status !== "running" ? result : null;
  return (
    <li
      className={clsx(
        "rounded-card border bg-surface px-4 py-3 transition-colors duration-200",
        finished?.status === "passed" ? "border-teal" : finished?.status === "failed" ? "border-danger" : "border-line",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-heading text-13 font-semibold text-muted tabular-nums">{item.id}</span>
        <StatusBadge result={result} />
      </div>
      <p className="mt-1 text-15 font-medium text-ink">{item.title}</p>
      {finished?.status === "failed" && <p className="mt-1 text-13 text-danger">{finished.observed}</p>}
      <details className="mt-1">
        <summary className="cursor-pointer rounded-sm text-13 font-medium text-teal">Details</summary>
        <div className="mt-2 flex flex-col gap-1">
          <Line label="Attack" text={item.attack} />
          <Line label="Expected" text={item.expected} />
          {finished && <Line label="Observed" text={finished.observed ?? ""} />}
        </div>
        {finished && (
          <ul className="mt-2 flex flex-col gap-1 border-t border-line pt-2">
            {finished.checks.map((check) => (
              <li key={check.label} className="flex items-start gap-2 text-13 text-body">
                {check.passed ? (
                  <Check aria-hidden className="mt-0.5 size-4 shrink-0 text-teal" />
                ) : (
                  <X aria-hidden className="mt-0.5 size-4 shrink-0 text-danger" />
                )}
                <span>
                  <span className="sr-only">{check.passed ? "Held: " : "Did not hold: "}</span>
                  {check.label}
                </span>
              </li>
            ))}
            {finished.evidence.map((entry) => (
              <li key={entry.seq} className="text-13 text-muted">
                Audit #{entry.seq}: {entry.label}
                {entry.summary && ` · ${entry.summary}`}
              </li>
            ))}
          </ul>
        )}
      </details>
    </li>
  );
}

/** The red-team suite: every attack run live against the real policy engine, on isolated copies of the database. */
export function RedTeam({ cases }: { cases: RedTeamCase[] }) {
  const [results, setResults] = useState<Record<string, RedTeamResult>>({});
  const [summary, setSummary] = useState<RedTeamSummary | null>(null);
  const [running, setRunning] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const stop = useRef<AbortController | null>(null);

  useEffect(() => () => stop.current?.abort(), []);
  useDemoCommands({ "security:run": () => run() });

  async function run() {
    const controller = new AbortController();
    stop.current = controller;
    setRunning(true);
    setProblem(null);
    setSummary(null);
    setResults({});
    try {
      await api.runRedTeam((event) => {
        if (event.event === "case") setResults((all) => ({ ...all, [event.data.id]: event.data }));
        else setSummary(event.data);
      }, controller.signal);
    } catch (failure) {
      if (controller.signal.aborted) return;
      setProblem(failure instanceof ApiError ? failure.message : "The suite could not be run.");
    } finally {
      if (!controller.signal.aborted) setRunning(false);
    }
  }

  return (
    <section id="red-team" aria-labelledby="red-team-title">
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <Button size="lg" icon={Play} loading={running} onClick={() => void run()}>
          Run red-team suite
        </Button>
        <p role="status" data-demo="redteam-score" className="text-24 font-semibold text-ink">
          {summary && (
            <>
              <span className="font-heading tabular-nums">
                {summary.passed} / {summary.total}
              </span>{" "}
              passed{" "}
              <span className="ml-1 text-13 font-normal text-muted">
                in {(summary.duration_ms / 1000).toFixed(1)} seconds
              </span>
            </>
          )}
          {problem && <span className="text-15 font-medium text-danger">{problem}</span>}
        </p>
        <div className="ml-auto text-right">
          <h2 id="red-team-title" className="sr-only">
            Red-team suite
          </h2>
          <p className="text-13 text-muted">
            Runs on an isolated copy of the database; your demo data is not affected.
          </p>
        </div>
      </div>
      <ul className="grid grid-cols-4 items-start gap-3">
        {cases.map((item) => (
          <CaseCard key={item.id} item={item} result={results[item.id]} />
        ))}
      </ul>
    </section>
  );
}
