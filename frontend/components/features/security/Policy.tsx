import {
  ArrowRight,
  Ban,
  CircleDollarSign,
  Link2,
  RefreshCw,
  Replace,
  ScanSearch,
  ShieldAlert,
  UserCheck,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { tierOf } from "@/components/features/assistant/StepCard";
import { Amount } from "@/components/ui/Amount";
import { Badge, TierBadge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import type { Currency, Limit, Safeguard, TierRow } from "@/lib/types";

/** T0 to T3 and Refused, exactly as the policy engine has them. */
export function TierTable({ tiers }: { tiers: TierRow[] }) {
  return (
    <Card title="Permission tiers">
      <table className="w-full text-left">
        <caption className="sr-only">Permission tiers of the policy engine</caption>
        <thead>
          <tr className="border-b border-line text-13 text-muted">
            <th scope="col" className="w-28 pb-2 font-medium">
              Tier
            </th>
            <th scope="col" className="w-24 pb-2 font-medium">
              Name
            </th>
            <th scope="col" className="w-80 pb-2 font-medium">
              Rule
            </th>
            <th scope="col" className="pb-2 font-medium">
              Tools
            </th>
          </tr>
        </thead>
        <tbody>
          {tiers.map((row) => (
            <tr key={row.tier} className="border-b border-line align-top last:border-b-0">
              <td className="py-3">
                <TierBadge tier={tierOf(row.tier)} />
              </td>
              <th scope="row" className="py-3 text-15 font-medium text-ink">
                {row.name}
              </th>
              <td className="py-3 pr-4 text-15 text-body">{row.rule}</td>
              <td className="py-3">
                {row.tools.length > 0 && (
                  <ul className="flex flex-wrap gap-1">
                    {row.tools.map((tool) => (
                      <li key={tool.name}>
                        <Badge>{tool.label}</Badge>
                      </li>
                    ))}
                  </ul>
                )}
                {row.tier === "T3" && (
                  <p className="mt-2 text-13 text-body">
                    Also: {row.raised_by.map((reason) => reason.title.toLowerCase()).join(" · ")}
                  </p>
                )}
                {row.tier === "REFUSED" && (
                  <details>
                    <summary className="cursor-pointer rounded-sm text-13 font-medium text-ink">
                      {row.raised_by.length} reasons
                    </summary>
                    <ul className="mt-2 flex flex-wrap gap-1">
                      {row.raised_by.map((reason) => (
                        <li key={reason.code}>
                          <Badge>{reason.title}</Badge>
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function limitValue(limit: Limit, currency: Currency) {
  if (limit.amount_minor !== null) return <Amount minor={limit.amount_minor} currency={currency} />;
  return <span className="font-heading tabular-nums">{limit.seconds} seconds</span>;
}

export function Limits({ limits, currency }: { limits: Limit[]; currency: Currency }) {
  return (
    <section aria-labelledby="your-limits">
      <h2 id="your-limits" className="mb-3 font-heading text-18 font-semibold text-ink">
        Your limits
      </h2>
      <ul className="grid grid-cols-4 gap-4">
        {limits.map((limit) => (
          <li key={limit.key} className="rounded-card border border-line bg-surface p-4">
            <p className="text-13 font-medium text-muted">{limit.label}</p>
            <p className="mt-1 text-24 font-semibold text-ink">{limitValue(limit, currency)}</p>
            <p className="mt-1 text-13 text-body">{limit.effect}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

const SAFEGUARD_ICONS: Record<string, LucideIcon> = {
  payee_verification: UserCheck,
  changed_details: Replace,
  scam_patterns: ScanSearch,
  injection_detection: ShieldAlert,
  money_mule: Ban,
  recheck_at_execution: RefreshCw,
  audit_log: Link2,
};

export function Safeguards({ safeguards }: { safeguards: Safeguard[] }) {
  return (
    <section aria-labelledby="safeguards">
      <h2 id="safeguards" className="mb-3 font-heading text-18 font-semibold text-ink">
        Safeguards
      </h2>
      <ul className="grid grid-cols-4 gap-4">
        {safeguards.map((item) => {
          const Icon = SAFEGUARD_ICONS[item.key] ?? CircleDollarSign;
          return (
            <li key={item.key} className="flex flex-col rounded-card border border-line bg-surface p-4">
              <p className="flex items-center gap-2 text-15 font-semibold text-ink">
                <Icon aria-hidden className="size-5 shrink-0 text-teal" strokeWidth={1.75} />
                {item.title}
              </p>
              <p className="mt-1 text-13 text-body">{item.text}</p>
              {item.key === "audit_log" && (
                <Link
                  href="/audit"
                  className="mt-auto inline-flex items-center gap-1 self-start rounded-sm pt-2 text-13 font-medium text-teal hover:underline"
                >
                  Open audit log
                  <ArrowRight aria-hidden className="size-4" />
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
