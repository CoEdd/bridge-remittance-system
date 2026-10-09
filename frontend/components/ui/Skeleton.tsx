import clsx from "clsx";

/** A placeholder block shown while content loads. Size it with `className`. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={clsx("block rounded-control bg-line motion-safe:animate-pulse", className)}
    />
  );
}
