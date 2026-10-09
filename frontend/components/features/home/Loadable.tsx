import type { ReactNode } from "react";
import { ErrorState } from "@/components/ui/ErrorState";
import type { ApiResult } from "@/lib/useApi";

interface LoadableProps<T> {
  result: ApiResult<T>;
  /** Skeleton shown while loading. */
  loading: ReactNode;
  /** Said to screen readers while loading, e.g. "Loading wallets". */
  loadingLabel: string;
  children: (data: T) => ReactNode;
}

/** Renders the loading, error or ready state of one backend call. */
export function Loadable<T>({ result, loading, loadingLabel, children }: LoadableProps<T>) {
  const { state, reload } = result;
  if (state.status === "loading") {
    return (
      <div role="status">
        {loading}
        <span className="sr-only">{loadingLabel}</span>
      </div>
    );
  }
  if (state.status === "error") {
    return <ErrorState message={state.message} onRetry={reload} />;
  }
  return <>{children(state.data)}</>;
}
