"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import type { AgentMode } from "@/lib/types";

type State = { kind: "loading" } | { kind: "ready"; mode: AgentMode } | { kind: "error" };

/** Shows "Agent: scripted" or "Agent: live", as reported by the backend's /health. */
export function AgentModeLabel() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    api
      .health(controller.signal)
      .then((health) => setState({ kind: "ready", mode: health.agent_mode }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ kind: "error" });
      });
    return () => controller.abort();
  }, [attempt]);

  if (state.kind === "loading") {
    return (
      <span role="status" className="flex items-center">
        <Skeleton className="h-6 w-32" />
        <span className="sr-only">Checking the agent mode</span>
      </span>
    );
  }

  if (state.kind === "error") {
    return (
      <span role="status" className="flex items-center gap-2">
        <Badge tone="danger">Agent: unavailable</Badge>
        <Button
          variant="ghost"
          icon={RefreshCw}
          onClick={() => {
            setState({ kind: "loading" });
            setAttempt((count) => count + 1);
          }}
        >
          Retry
        </Button>
      </span>
    );
  }

  return (
    <span role="status">
      <Badge>Agent: {state.mode}</Badge>
    </span>
  );
}
