"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import { formatTimestampUtc } from "@/lib/format";
import type { AuditEntry } from "@/lib/types";

/** "3349376f7369…673747884a": enough to compare by eye; Copy gives the full value. */
function shorten(hash: string): string {
  return `${hash.slice(0, 12)}…${hash.slice(-10)}`;
}

function HashRow({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="flex items-center justify-between gap-4 border-t border-line py-3">
      <div>
        <p className="text-13 text-muted">{label}</p>
        <p className="font-heading text-15 text-ink tabular-nums" title={value}>
          {shorten(value)}
        </p>
      </div>
      <Button variant="secondary" icon={copied ? Check : Copy} onClick={() => void copy()}>
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}

interface EntrySheetProps {
  entry: AuditEntry | null;
  onClose: () => void;
}

/** Full detail of one audit entry: payload and both hashes. */
export function EntrySheet({ entry, onClose }: EntrySheetProps) {
  return (
    <Sheet open={entry !== null} onClose={onClose} title={entry ? `Entry #${entry.seq}` : ""}>
      {entry && (
        <>
          <p className="text-18 font-semibold text-ink">{entry.label}</p>
          <p className="text-13 text-muted">
            {entry.event_type} · {entry.actor} · {formatTimestampUtc(entry.created_at)}
          </p>
          <h3 className="mt-6 mb-2 text-13 font-medium text-muted">Payload</h3>
          <pre
            tabIndex={0}
            className="max-h-80 overflow-auto rounded-control border border-line bg-paper p-4 text-13 text-ink"
          >
            {JSON.stringify(entry.payload, null, 2)}
          </pre>
          <div className="mt-6">
            <HashRow label="Previous hash" value={entry.prev_hash} />
            <HashRow label="Hash" value={entry.hash} />
          </div>
        </>
      )}
    </Sheet>
  );
}
