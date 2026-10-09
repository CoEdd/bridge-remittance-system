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

// Fixed month names, so every browser and the server print the same text.
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function twoDigits(value: number): string {
  return String(value).padStart(2, "0");
}

/** Formats a calendar date "YYYY-MM-DD" as "15 Nov 2026". No time zone shift. */
export function formatDate(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  const month = match ? MONTHS[Number(match[2]) - 1] : undefined;
  if (!match || !month) throw new RangeError(`Not a calendar date: ${isoDate}`);
  return `${Number(match[3])} ${month} ${match[1]}`;
}

/** Formats a UTC timestamp as "9 Oct 2026, 03:15:42 UTC", for rates and audit-log entries. */
export function formatTimestampUtc(isoTimestamp: string): string {
  const instant = new Date(isoTimestamp);
  if (Number.isNaN(instant.getTime())) throw new RangeError(`Not a timestamp: ${isoTimestamp}`);
  const day = `${instant.getUTCDate()} ${MONTHS[instant.getUTCMonth()]} ${instant.getUTCFullYear()}`;
  const time = [instant.getUTCHours(), instant.getUTCMinutes(), instant.getUTCSeconds()]
    .map(twoDigits)
    .join(":");
  return `${day}, ${time} UTC`;
}
