import clsx from "clsx";
import { formatAmount } from "@/lib/format";
import type { Currency } from "@/lib/types";

interface AmountProps {
  /** Integer amount in minor units (sen, fen, cents). */
  minor: number;
  currency: Currency;
  className?: string;
}

/** A money amount with its currency code, e.g. "CNY 12,000.00", in tabular numerals. */
export function Amount({ minor, currency, className }: AmountProps) {
  return (
    <span className={clsx("font-heading tabular-nums whitespace-nowrap", className)}>
      {formatAmount(minor, currency)}
    </span>
  );
}
