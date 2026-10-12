import {
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
import { tierOf } from "@/components/features/assistant/Steps";
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
            <th scope="col" className="w-96 pb-2 font-medium">
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
              <td className="py-2">
                <TierBadge tier={tierOf(row.tier)} />
              </td>
              <th scope="row" className="py-2 text-15 font-medium text-ink">
                {row.name}
              </th>
              <td className="py-2 pr-4 text-15 text-body">{row.rule}</td>
              <td className="py-2">
                {row.tools.length > 0 && (
                  <ul className="flex flex-wrap gap-1">
                    {row.tools.map((tool) => (
                      <li key={tool.name}>
                        <Badge>{tool.label}</Badge>
                      </li>
                    ))}
                  </ul>
                )}
                {row.raised_by.length > 0 && (
                  <details className={row.tools.length > 0 ? "mt-1" : undefined}>
                    <summary className="cursor-pointer rounded-sm text-13 font-medium text-teal">
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
    <Card title="Your limits">
      <ul className="grid grid-cols-4 gap-4">
        {limits.map((limit) => (
          <li key={limit.key}>
            <p className="text-13 font-medium text-muted">{limit.label}</p>
            <p className="text-18 font-semibold text-ink">{limitValue(limit, currency)}</p>
            <p className="text-13 text-body">{limit.effect}</p>
          </li>
        ))}
      </ul>
    </Card>
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

/** The safeguards by name. What each one does opens on request. */
export function Safeguards({ safeguards }: { safeguards: Safeguard[] }) {
  return (
    <Card title="Safeguards">
      <ul className="flex flex-wrap gap-2">
        {safeguards.map((item) => {
          const Icon = SAFEGUARD_ICONS[item.key] ?? CircleDollarSign;
          return (
            <li
              key={item.key}
              className="inline-flex h-8 items-center gap-2 rounded-full border border-line bg-paper px-3 text-13 font-medium text-ink"
            >
              <Icon aria-hidden className="size-4 text-teal" strokeWidth={1.75} />
              {item.title}
            </li>
          );
        })}
      </ul>
      <details className="mt-3">
        <summary className="cursor-pointer rounded-sm text-13 font-medium text-teal">What each one does</summary>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-13">
          {safeguards.map((item) => (
            <div key={item.key} className="contents">
              <dt className="font-medium text-ink">{item.title}</dt>
              <dd className="text-body">{item.text}</dd>
            </div>
          ))}
        </dl>
      </details>
    </Card>
  );
}
