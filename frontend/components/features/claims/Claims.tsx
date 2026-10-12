import { BadgeCheck, CircleHelp, CircleX, TriangleAlert, type LucideIcon } from "lucide-react";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import type { ClaimCheck, ClaimReasoning, ClaimRow, ClaimStatus, Language } from "@/lib/types";

const STATUS: Record<ClaimStatus, { label: string; tone: BadgeTone; icon: LucideIcon }> = {
  supported: { label: "Supported", tone: "success", icon: BadgeCheck },
  contradicted: { label: "Contradicted", tone: "danger", icon: CircleX },
  flagged: { label: "Flagged", tone: "warning", icon: TriangleAlert },
  unverifiable: { label: "Unverifiable", tone: "neutral", icon: CircleHelp },
};

/** Says honestly where the claims came from. */
export const ORIGINS: Record<NonNullable<ClaimCheck["origin"]>, string> = {
  live: "Claims: extracted live",
  cached: "Claims: cached from a live run",
  regex: "Claims: regex extractor",
};

function StatusBadge({ status }: { status: ClaimStatus }) {
  const { label, tone, icon } = STATUS[status];
  return (
    <Badge tone={tone} icon={icon}>
      {label}
    </Badge>
  );
}

/** The claims at a glance: one line each, what it says and how it was judged. */
export function ClaimList({ claims, shown }: { claims: ClaimRow[]; shown: Language }) {
  return (
    <ul className="flex flex-col gap-1">
      {claims.map((claim, index) => (
        <li key={index} className="flex items-center justify-between gap-3" title={`“${claim.source}”`}>
          <span lang={shown} className="min-w-0 truncate text-15 text-ink">
            {claim.meaning[shown]}
          </span>
          <StatusBadge status={claim.status} />
        </li>
      ))}
    </ul>
  );
}

/** Every claim in full: the quoted text, what it means, its status and the fact behind it. */
export function ClaimTable({ claims, shown }: { claims: ClaimRow[]; shown: Language }) {
  return (
    <table className="w-full text-left">
      <caption className="sr-only">Claims this document makes, and how each was judged</caption>
      <thead>
        <tr className="border-b border-line text-13 text-muted">
          {["Claim", "Meaning", "Status", "Evidence"].map((heading) => (
            <th key={heading} scope="col" className="pr-4 pb-2 font-medium last:pr-0">
              {heading}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {claims.map((claim, index) => (
          <tr key={index} className="border-b border-line align-top last:border-b-0">
            <td className="max-w-64 py-2 pr-4 text-13 break-words text-body">“{claim.source}”</td>
            <td lang={shown} className="py-2 pr-4 text-15 text-ink">
              {claim.meaning[shown]}
            </td>
            <td className="py-2 pr-4">
              <StatusBadge status={claim.status} />
            </td>
            <td className="py-2 text-13 text-body">
              {claim.evidence ? (
                <>
                  <span lang={shown}>{claim.evidence.words[shown]}</span>
                  <span className="block text-muted">{claim.evidence.source}</span>
                </>
              ) : (
                "None"
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** "Show reasoning": the chain behind each conclusion, in plain words. */
export function Reasoning({ items, shown }: { items: ClaimReasoning[]; shown: Language }) {
  if (items.length === 0) return null;
  return (
    <details>
      <summary className="cursor-pointer rounded-sm text-13 font-medium text-teal">Show reasoning</summary>
      <ol className="mt-2 flex flex-col gap-3">
        {items.map((item) => (
          <li key={item.rule} lang={shown} className="text-13 text-body">
            <span className="font-medium text-ink">
              {item.rule} · {item.title[shown]}
            </span>
            {item.lines[shown].map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
          </li>
        ))}
      </ol>
    </details>
  );
}
