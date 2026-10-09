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

/**
 * Loads data from the backend when the component mounts.
 * Pass a stable function (for example `api.accounts`), not one created on each render.
 */
export function useApi<T>(load: (signal: AbortSignal) => Promise<T>): ApiResult<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal)
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof ApiError ? error.message : "Something went wrong.";
        setState({ status: "error", message });
      });
    return () => controller.abort();
  }, [load, attempt]);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((count) => count + 1);
  }, []);

  return { state, reload };
}
