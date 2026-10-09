import clsx from "clsx";
import { Badge } from "@/components/ui/Badge";
import { formatTimestampUtc } from "@/lib/format";
import type { AuditEntry } from "@/lib/types";

const ACTOR_LABELS: Record<AuditEntry["actor"], string> = {
  agent: "Agent",
  policy: "Policy",
  user: "User",
  system: "System",
};

interface AuditTableProps {
  entries: AuditEntry[];
  onOpen: (entry: AuditEntry) => void;
  /** In the tampering simulation: the entry where the chain breaks. */
  brokenSeq?: number;
}

export function AuditTable({ entries, onOpen, brokenSeq }: AuditTableProps) {
  return (
    <table className="w-full text-left">
      <caption className="sr-only">Audit entries, newest first</caption>
      <thead>
        <tr className="border-b border-line text-13 text-muted">
          <th scope="col" className="w-16 pb-2 font-medium">
            #
          </th>
          <th scope="col" className="w-56 pb-2 font-medium">
            Time
          </th>
          <th scope="col" className="w-24 pb-2 font-medium">
            Actor
          </th>
          <th scope="col" className="w-48 pb-2 font-medium">
            Event
          </th>
          <th scope="col" className="pb-2 font-medium">
            Summary
          </th>
        </tr>
      </thead>
      <tbody>
        {entries.map((entry) => {
          const broken = entry.seq === brokenSeq;
          return (
            <tr
              key={entry.seq}
              onClick={() => onOpen(entry)}
              className={clsx(
                "cursor-pointer border-b border-line align-top transition-colors duration-150 last:border-b-0",
                broken ? "bg-danger-tint" : "hover:bg-paper",
              )}
            >
              <td className="py-3">
                <button
                  type="button"
                  aria-label={`Open entry ${entry.seq}`}
                  className="rounded-sm font-heading text-15 font-medium text-ink tabular-nums underline-offset-4 hover:underline"
                >
                  #{entry.seq}
                </button>
              </td>
              <td className="py-3 text-13 text-muted">{formatTimestampUtc(entry.created_at)}</td>
              <td className="py-3 text-15 text-body">{ACTOR_LABELS[entry.actor]}</td>
              <td className="py-3">
                <span className="block text-15 text-ink">{entry.label}</span>
                <span className="block text-13 text-muted">{entry.event_type}</span>
              </td>
              <td className="py-3 text-15 text-body">
                {broken && (
                  <span className="mr-2">
                    <Badge tone="danger">Broken</Badge>
                  </span>
                )}
                {entry.summary}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
