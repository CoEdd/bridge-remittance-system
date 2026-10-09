"use client";

import { CalendarDays, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";

/**
 * Two facts from the backend's /health: who drives the agent ("scripted" or "live",
 * with a note when live mode fell back for lack of an API key) and the fixed demo
 * date, so nobody is confused by the dates on screen.
 */
export function HeaderStatus() {
  const { state, reload } = useApi(api.health);

  if (state.status === "loading") {
    return (
      <span role="status" className="flex items-center gap-2">
        <Skeleton className="h-6 w-28" />
        <Skeleton className="h-6 w-40" />
        <span className="sr-only">Checking the backend</span>
      </span>
    );
  }

  if (state.status === "error") {
    return (
      <span role="status" className="flex items-center gap-2">
        <Badge tone="danger">Backend unavailable</Badge>
        <Button variant="ghost" icon={RefreshCw} onClick={reload}>
          Retry
        </Button>
      </span>
    );
  }

  return (
    <span role="status" className="flex items-center gap-2">
      <Badge>
        Agent: {state.data.agent_mode}
        {state.data.agent_note ? ` (${state.data.agent_note})` : ""}
      </Badge>
      <Badge icon={CalendarDays}>Demo date: {formatDate(state.data.demo_today)}</Badge>
    </span>
  );
}
