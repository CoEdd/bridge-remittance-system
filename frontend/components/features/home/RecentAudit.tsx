"use client";

import { ArrowRight, ScrollText } from "lucide-react";
import Link from "next/link";
import { Loadable } from "@/components/features/home/Loadable";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { formatTimestampUtc } from "@/lib/format";
import { useApi } from "@/lib/useApi";

const RECENT_COUNT = 3;

function loadRecent(signal: AbortSignal) {
  return api.audit({ page_size: RECENT_COUNT }, signal);
}

function AuditLink() {
  return (
    <Link href="/audit" className={buttonClasses("secondary")}>
      Open audit log
      <ArrowRight aria-hidden className="size-4" />
    </Link>
  );
}

export function RecentAudit() {
  const result = useApi(loadRecent);

  return (
    <Card title="Recent audit events">
      <Loadable
        result={result}
        loadingLabel="Loading audit events"
        loading={
          <div className="flex flex-col gap-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        }
      >
        {(data) =>
          data.entries.length === 0 ? (
            <EmptyState icon={ScrollText} message="The audit log is empty." action={<AuditLink />} />
          ) : (
            <>
              <ul className="mb-4 flex flex-col">
                {data.entries.map((entry) => (
                  <li
                    key={entry.seq}
                    className="border-t border-line py-3 first:border-t-0 first:pt-0"
                  >
                    <p className="flex items-baseline justify-between gap-4">
                      <span className="text-15 font-medium text-ink">{entry.label}</span>
                      <span className="text-13 whitespace-nowrap text-muted">
                        {formatTimestampUtc(entry.created_at)}
                      </span>
                    </p>
                    <p className="text-13 text-muted">{entry.summary}</p>
                  </li>
                ))}
              </ul>
              <AuditLink />
            </>
          )
        }
      </Loadable>
    </Card>
  );
}
