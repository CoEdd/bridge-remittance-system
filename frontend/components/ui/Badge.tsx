import clsx from "clsx";
import { Ban, KeyRound, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "success" | "warning" | "danger";

const TONES: Record<BadgeTone, string> = {
  neutral: "border-line bg-paper text-body",
  success: "border-teal bg-teal-tint text-ink",
  warning: "border-amber-line bg-amber-tint text-amber-ink",
  danger: "border-danger bg-danger-tint text-danger",
};

interface BadgeProps {
  tone?: BadgeTone;
  icon?: LucideIcon;
  /** The word the badge carries. Colour is never the only signal. */
  children: ReactNode;
}

export function Badge({ tone = "neutral", icon: Icon, children }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex h-6 items-center gap-1 rounded-full border px-2 text-13 font-medium whitespace-nowrap",
        TONES[tone],
      )}
    >
      {Icon && <Icon aria-hidden className="size-3.5" />}
      {children}
    </span>
  );
}

export type Tier = "T0" | "T1" | "T2" | "T3" | "Blocked";

const TIERS: Record<Tier, { label: string; tone: BadgeTone; icon?: LucideIcon }> = {
  T0: { label: "Tier 0", tone: "neutral" },
  T1: { label: "Tier 1", tone: "neutral" },
  T2: { label: "Tier 2", tone: "warning" },
  T3: { label: "Tier 3", tone: "warning", icon: KeyRound },
  Blocked: { label: "Blocked", tone: "danger", icon: Ban },
};

/** Permission tier of an action, as decided by the policy engine. */
export function TierBadge({ tier }: { tier: Tier }) {
  const { label, tone, icon } = TIERS[tier];
  return (
    <Badge tone={tone} icon={icon}>
      {label}
    </Badge>
  );
}
