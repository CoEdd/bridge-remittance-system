import type { Currency } from "./types";

/** Decimal places of each currency's minor unit (sen, fen, cents). */
const MINOR_DIGITS: Record<Currency, number> = { MYR: 2, CNY: 2, USD: 2 };

/**
 * Formats an integer amount in minor units, e.g. (1200000, "CNY") -> "CNY 12,000.00".
 * Uses integer arithmetic only, so no rounding can creep in.
 */
export function formatAmount(minor: number, currency: Currency): string {
  if (!Number.isSafeInteger(minor)) {
    throw new RangeError("An amount must be a whole number of minor units.");
  }
  const digits = MINOR_DIGITS[currency];
  const unit = 10 ** digits;
  const absolute = Math.abs(minor);
  const fraction = absolute % unit;
  const whole = (absolute - fraction) / unit;
  const grouped = String(whole).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const sign = minor < 0 ? "-" : "";
  return `${currency} ${sign}${grouped}.${String(fraction).padStart(digits, "0")}`;
}

const DATE_FORMAT = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

const TIME_FORMAT = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
  timeZone: "UTC",
});

/** Formats a calendar date "YYYY-MM-DD" as "15 Nov 2026". No time zone shift. */
export function formatDate(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!match) throw new RangeError(`Not a calendar date: ${isoDate}`);
  const [, year, month, day] = match;
  return DATE_FORMAT.format(new Date(Date.UTC(Number(year), Number(month) - 1, Number(day))));
}

/** Formats a UTC timestamp as "9 Oct 2026, 03:15:42 UTC", for audit-log entries. */
export function formatTimestampUtc(isoTimestamp: string): string {
  const instant = new Date(isoTimestamp);
  if (Number.isNaN(instant.getTime())) throw new RangeError(`Not a timestamp: ${isoTimestamp}`);
  return `${DATE_FORMAT.format(instant)}, ${TIME_FORMAT.format(instant)} UTC`;
}
