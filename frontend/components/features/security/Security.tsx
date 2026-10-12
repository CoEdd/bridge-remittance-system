"use client";

import { useCallback } from "react";
import { Loadable } from "@/components/features/home/Loadable";
import { Limits, Safeguards, TierTable } from "@/components/features/security/Policy";
import { RedTeam } from "@/components/features/security/RedTeam";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";

/** The Security page: what the policy engine allows, the student's limits, the safeguards and the red-team suite. */
export function Security() {
  const load = useCallback(
    (signal: AbortSignal) => Promise.all([api.securityPolicy(signal), api.redTeamCases(signal)]),
    [],
  );
  const result = useApi(load);

  return (
    <Loadable
      result={result}
      loadingLabel="Loading the security page"
      loading={
        <div className="flex flex-col gap-6">
          <Skeleton className="h-72 w-full" />
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      }
    >
      {([policy, cases]) => (
        <div className="flex flex-col gap-8">
          <TierTable tiers={policy.tiers} />
          <Limits limits={policy.limits} currency={policy.currency} />
          <Safeguards safeguards={policy.safeguards} />
          <RedTeam cases={cases} />
        </div>
      )}
    </Loadable>
  );
}
