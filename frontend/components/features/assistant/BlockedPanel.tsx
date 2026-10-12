"use client";

import { ArrowRight, Ban, Languages, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PolicyQuote } from "@/components/features/documents/PolicyQuote";
import { Button } from "@/components/ui/Button";
import { LANGUAGE_NAMES } from "@/lib/language";
import type { BlockedEvent, Language } from "@/lib/types";

/** Why a payment was refused: one row per reason, the policy clause that proves it, and what to do instead. */
export function BlockedPanel({ blocked, language }: { blocked: BlockedEvent; language: Language }) {
  const [english, setEnglish] = useState(false);
  const shown: Language = english ? "en" : language;
  // The reasons were written in the student's language when the payment was blocked.
  const translated = blocked.reasons.some((reason) => reason.text !== reason.text_en);

  return (
    <section
      aria-label="Payment blocked"
      className="overflow-hidden rounded-card border border-danger bg-surface motion-safe:animate-step-in"
    >
      <h3 className="flex items-center gap-2 bg-danger-tint px-4 py-3 font-heading text-18 font-semibold text-danger">
        <Ban aria-hidden className="size-5 shrink-0" />
        Payment blocked: no money was moved
      </h3>
      <ul className="flex flex-col gap-4 px-4 py-4">
        {blocked.reasons.map((reason) => (
          <li key={reason.code} className="grid grid-cols-[auto_1fr] gap-3">
            <TriangleAlert aria-hidden className="mt-0.5 size-5 text-danger" strokeWidth={1.75} />
            <div lang={shown}>
              <p className="text-15 font-semibold text-ink">{english ? reason.title_en : reason.title}</p>
              <p className="text-15 text-body">{english ? reason.text_en : reason.text}</p>
              {reason.policy_clause && <PolicyQuote clause={reason.policy_clause} shown={shown} />}
            </div>
          </li>
        ))}
      </ul>
      <div className="flex flex-col gap-2 border-t border-line px-4 py-3">
        <p lang={shown} className="text-15 font-medium text-ink">
          {english ? blocked.advice_en : blocked.advice}
        </p>
        <div className="flex flex-wrap items-center justify-between gap-2">
          {blocked.audit_seq !== null && (
            <Link
              href={`/audit?entry=${blocked.audit_seq}`}
              className="inline-flex items-center gap-1 rounded-sm text-13 font-medium text-teal hover:underline"
            >
              View in audit log
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          )}
          {translated && (
            <Button variant="ghost" size="sm" icon={Languages} onClick={() => setEnglish(!english)}>
              {english ? `Show ${LANGUAGE_NAMES[language]}` : "Show English"}
            </Button>
          )}
        </div>
      </div>
    </section>
  );
}
