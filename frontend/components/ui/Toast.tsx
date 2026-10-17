"use client";

import { ArrowDownLeft } from "lucide-react";
import { useEffect } from "react";

const SHOW_MS = 5000;

/** A short notice in the top right corner that closes by itself, like a phone's notification. */
export function Toast({ message, onDone }: { message: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(onDone, SHOW_MS);
    return () => clearTimeout(timer);
  }, [message, onDone]);

  if (!message) return null;
  return (
    <div
      role="status"
      className="fixed top-28 right-8 z-40 flex items-center gap-3 rounded-card border border-teal bg-surface px-4 py-3 text-15 font-medium text-ink shadow-overlay motion-safe:animate-step-in"
    >
      <span aria-hidden className="flex size-8 items-center justify-center rounded-full bg-teal-tint text-teal">
        <ArrowDownLeft className="size-4" />
      </span>
      {message}
    </div>
  );
}
