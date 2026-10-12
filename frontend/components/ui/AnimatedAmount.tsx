"use client";

import { useEffect, useRef, useState } from "react";
import { Amount } from "./Amount";
import type { Currency } from "@/lib/types";

const DURATION_MS = 250;

interface AnimatedAmountProps {
  /** Integer amount in minor units. When it changes, the number runs to the new value. */
  minor: number;
  currency: Currency;
  className?: string;
}

/** An amount that moves smoothly to its new value, so a balance change is seen, not missed. */
export function AnimatedAmount({ minor, currency, className }: AnimatedAmountProps) {
  const [shown, setShown] = useState(minor);
  const shownRef = useRef(minor);

  useEffect(() => {
    const from = shownRef.current;
    if (from === minor) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      shownRef.current = minor;
      setShown(minor);
      return;
    }
    const start = performance.now();
    let frame = 0;
    function tick(now: number) {
      const progress = Math.min(1, (now - start) / DURATION_MS);
      const eased = 1 - (1 - progress) ** 3;
      const value = progress === 1 ? minor : Math.round(from + (minor - from) * eased);
      shownRef.current = value;
      setShown(value);
      if (progress < 1) frame = requestAnimationFrame(tick);
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [minor]);

  return <Amount minor={shown} currency={currency} className={className} />;
}
