"use client";

import clsx from "clsx";
import { cloneElement, useId, useState, type ReactElement } from "react";

interface TooltipProps {
  label: string;
  /** One focusable element, such as a button. It is described by the tooltip. */
  children: ReactElement<{ "aria-describedby"?: string }>;
}

/** A short hint shown on hover and on keyboard focus. Esc hides it. */
export function Tooltip({ label, children }: TooltipProps) {
  const id = useId();
  const [open, setOpen] = useState(false);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
      }}
    >
      {cloneElement(children, { "aria-describedby": id })}
      <span
        id={id}
        role="tooltip"
        className={clsx(
          "pointer-events-none absolute top-full left-1/2 z-40 mt-2 -translate-x-1/2 rounded-control border border-line bg-surface px-3 py-1 text-13 whitespace-nowrap text-ink shadow-overlay transition-opacity duration-150",
          open ? "opacity-100" : "invisible opacity-0",
        )}
      >
        {label}
      </span>
    </span>
  );
}
