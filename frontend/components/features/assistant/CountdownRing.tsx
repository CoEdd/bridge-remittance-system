"use client";

import { useEffect, useState } from "react";

const RADIUS = 44;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

interface CountdownRingProps {
  /** UTC timestamp at which the wait is over. */
  until: string;
  totalSeconds: number;
}

/** A ring that empties as a cooling-off wait runs down, with the seconds left in the middle. */
export function CountdownRing({ until, totalSeconds }: CountdownRingProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(timer);
  }, []);

  const left = Math.max(0, Math.ceil((new Date(until).getTime() - now) / 1000));
  const fraction = totalSeconds > 0 ? Math.min(1, left / totalSeconds) : 0;

  return (
    <div role="timer" aria-label={`${left} seconds left`} className="relative size-32">
      <svg aria-hidden viewBox="0 0 100 100" className="size-full -rotate-90">
        <circle cx="50" cy="50" r={RADIUS} fill="none" strokeWidth="6" className="stroke-line" />
        <circle
          cx="50"
          cy="50"
          r={RADIUS}
          fill="none"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={CIRCUMFERENCE * (1 - fraction)}
          className="stroke-amber-line transition-[stroke-dashoffset] duration-200 ease-linear"
        />
      </svg>
      <span aria-hidden className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-heading text-32 font-bold text-ink tabular-nums">{left}</span>
        <span className="text-13 text-muted">seconds left</span>
      </span>
    </div>
  );
}
