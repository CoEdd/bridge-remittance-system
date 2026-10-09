"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./api";

export type AsyncState<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: T };

export interface ApiResult<T> {
  state: AsyncState<T>;
  /** Fetch again, for a "Try again" button. */
  reload: () => void;
}

// If the backend cannot be reached (it is starting or restarting), keep showing the
// loading state and try again after each of these waits, about 12 seconds in all,
// before showing an error.
const RETRY_WAITS_MS = [1000, 1500, 2000, 2500, 2500, 2500];

/**
 * Loads data from the backend when the component mounts.
 * Pass a stable function (for example `api.accounts`), not one created on each render.
 */
export function useApi<T>(load: (signal: AbortSignal) => Promise<T>): ApiResult<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let retries = 0;

    function run() {
      load(controller.signal)
        .then((data) => setState({ status: "ready", data }))
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          const unreachable = error instanceof ApiError && error.status === null;
          if (unreachable && retries < RETRY_WAITS_MS.length) {
            timer = setTimeout(run, RETRY_WAITS_MS[retries]);
            retries += 1;
            return;
          }
          const message = error instanceof ApiError ? error.message : "Something went wrong.";
          setState({ status: "error", message });
        });
    }

    run();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [load, attempt]);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((count) => count + 1);
  }, []);

  return { state, reload };
}
