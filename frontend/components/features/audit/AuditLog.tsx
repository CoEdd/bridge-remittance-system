"use client";

import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  FlaskConical,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { useCallback, useEffect, useId, useState } from "react";
import { useDemoCommands } from "@/lib/demo";
import { AuditTable } from "@/components/features/audit/AuditTable";
import { EntrySheet } from "@/components/features/audit/EntrySheet";
import { Loadable } from "@/components/features/home/Loadable";
import { Badge } from "@/components/ui/Badge";
import { Button, buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApiError, api } from "@/lib/api";
import type { AuditEntry, AuditVerify, TamperResult } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const PAGE_SIZE = 50;

type VerifyState =
  | { status: "idle" }
  | { status: "running" }
  | { status: "done"; result: AuditVerify }
  | { status: "failed"; message: string };

function VerifyResult({ check }: { check: VerifyState }) {
  if (check.status === "done" && check.result.ok) {
    return (
      <Badge tone="success" icon={ShieldCheck}>
        Chain intact · {check.result.entries} entries
      </Badge>
    );
  }
  if (check.status === "done") {
    return (
      <Badge tone="danger" icon={ShieldAlert}>
        Chain broken at entry #{check.result.broken_at}
      </Badge>
    );
  }
  if (check.status === "failed") return <Badge tone="danger">{check.message}</Badge>;
  return null;
}

/** The temporary view of a tampered copy. Nothing here touches the real log. */
function Simulation({
  result,
  onBack,
  onOpen,
}: {
  result: TamperResult;
  onBack: () => void;
  onOpen: (entry: AuditEntry) => void;
}) {
  return (
    <Card className="border-danger">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Badge tone="danger" icon={ShieldAlert}>
            Chain broken at entry #{result.verification.broken_at}
          </Badge>
          <span className="text-13 text-muted">Simulation on a copy; the real log is not changed</span>
        </div>
        <Button variant="secondary" icon={ArrowLeft} onClick={onBack}>
          Back to real log
        </Button>
      </div>
      <p className="mt-4 mb-6 text-15 text-body">
        Entry #{result.seq}: <span className="font-medium text-ink">{result.field}</span> changed from{" "}
        <span className="font-medium text-ink">{String(result.original)}</span> to{" "}
        <span className="font-medium text-ink">{String(result.tampered)}</span>. Its hash no longer
        matches.
      </p>
      <AuditTable entries={result.entries} onOpen={onOpen} brokenSeq={result.verification.broken_at ?? undefined} />
    </Card>
  );
}

/** `initialEntry` opens one entry straight away, for links from the Assistant. */
export function AuditLog({ initialEntry = null }: { initialEntry?: number | null }) {
  const filterId = useId();
  const [page, setPage] = useState(1);
  const [eventType, setEventType] = useState("");
  const [opened, setOpened] = useState<AuditEntry | null>(null);
  const [check, setCheck] = useState<VerifyState>({ status: "idle" });
  const [simulation, setSimulation] = useState<TamperResult | null>(null);
  const [simulating, setSimulating] = useState(false);

  const load = useCallback(
    (signal: AbortSignal) =>
      api.audit({ page, page_size: PAGE_SIZE, event_type: eventType || undefined }, signal),
    [page, eventType],
  );
  const result = useApi(load);

  useEffect(() => {
    if (initialEntry === null) return;
    const controller = new AbortController();
    api
      .audit({ seq: initialEntry }, controller.signal)
      .then((found) => setOpened(found.entries[0] ?? null))
      .catch(() => {
        // The table below still loads; only the shortcut to one entry is lost.
      });
    return () => controller.abort();
  }, [initialEntry]);

  async function verify() {
    setCheck({ status: "running" });
    try {
      setCheck({ status: "done", result: await api.verifyAudit() });
    } catch (error) {
      setCheck({ status: "failed", message: error instanceof ApiError ? error.message : "Check failed" });
    }
  }

  // The demo bar's "Audit proof" step: the chain is intact, then a changed copy shows where it breaks.
  useDemoCommands({
    "audit:proof": async () => {
      await verify();
      await new Promise((resolve) => setTimeout(resolve, 1200)); // time to read "intact"
      await simulate();
    },
  });

  async function simulate() {
    setSimulating(true);
    try {
      setSimulation(await api.simulateTamper());
    } catch (error) {
      setCheck({ status: "failed", message: error instanceof ApiError ? error.message : "Simulation failed" });
    } finally {
      setSimulating(false);
    }
  }

  return (
    <>
      <Card className="mb-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3" role="status">
            <Button icon={ShieldCheck} loading={check.status === "running"} onClick={() => void verify()}>
              Verify chain
            </Button>
            {!simulation && <VerifyResult check={check} />}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" icon={FlaskConical} loading={simulating} onClick={() => void simulate()}>
              Simulate tampering
            </Button>
            <a href={api.auditExportUrl("json")} className={buttonClasses("secondary")}>
              <Download aria-hidden className="size-4" />
              Export JSON
            </a>
            <a href={api.auditExportUrl("csv")} className={buttonClasses("secondary")}>
              <Download aria-hidden className="size-4" />
              Export CSV
            </a>
          </div>
        </div>
        {!simulation && (
          <p className="mt-3 text-right text-13 text-muted">
            Simulation on a copy; the real log is not changed
          </p>
        )}
      </Card>

      {simulation ? (
        <div data-demo="tamper">
          <Simulation result={simulation} onBack={() => setSimulation(null)} onOpen={setOpened} />
        </div>
      ) : (
        <Card>
          <Loadable
            result={result}
            loadingLabel="Loading the audit log"
            loading={
              <div className="flex flex-col gap-3">
                {[0, 1, 2, 3].map((key) => (
                  <Skeleton key={key} className="h-10 w-full" />
                ))}
              </div>
            }
          >
            {(data) => {
              const pages = Math.max(1, Math.ceil(data.total / data.page_size));
              return (
                <>
                  <div className="mb-4 flex items-center justify-between gap-4">
                    <div className="flex items-center gap-2">
                      <label htmlFor={filterId} className="text-13 text-muted">
                        Event
                      </label>
                      <select
                        id={filterId}
                        value={eventType}
                        onChange={(event) => {
                          setEventType(event.target.value);
                          setPage(1);
                        }}
                        className="h-10 rounded-control border border-line bg-surface px-3 text-15 text-ink"
                      >
                        <option value="">All events</option>
                        {data.event_types.map((type) => (
                          <option key={type.code} value={type.code}>
                            {type.label}
                          </option>
                        ))}
                      </select>
                      <span className="text-13 text-muted">
                        {data.total} {data.total === 1 ? "entry" : "entries"}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        icon={ChevronLeft}
                        disabled={page <= 1}
                        onClick={() => setPage(page - 1)}
                      >
                        Previous
                      </Button>
                      <span className="text-13 text-muted">
                        Page {data.page} of {pages}
                      </span>
                      <Button variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                        Next
                        <ChevronRight aria-hidden className="size-4" />
                      </Button>
                    </div>
                  </div>
                  {data.entries.length === 0 ? (
                    <EmptyState
                      icon={ScrollText}
                      message="No entries of this type yet."
                      action={
                        <Button variant="secondary" onClick={() => setEventType("")}>
                          Show all events
                        </Button>
                      }
                    />
                  ) : (
                    <AuditTable entries={data.entries} onOpen={setOpened} />
                  )}
                </>
              );
            }}
          </Loadable>
        </Card>
      )}

      <EntrySheet entry={opened} onClose={() => setOpened(null)} />
    </>
  );
}
