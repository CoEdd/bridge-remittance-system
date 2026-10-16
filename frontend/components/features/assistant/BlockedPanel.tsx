"use client";

import { ArrowRight, Ban, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { lead } from "@/components/features/assistant/model";
import { ClaimList, Reasoning } from "@/components/features/claims/Claims";
import { PolicyQuote } from "@/components/features/documents/PolicyQuote";
import { Button } from "@/components/ui/Button";
import { useGlosses } from "@/lib/demo";
import { LANGUAGE_NAMES } from "@/lib/language";
import type { BlockedEvent, Language } from "@/lib/types";

/**
 * Why a payment was refused, at a glance. When the claim check found something: each claim
 * that counts against the payment and its status, with the chain behind "Show reasoning".
 * Otherwise the reasons by name, with "Why?" for the explanation.
 */
export function BlockedPanel({ blocked, language }: { blocked: BlockedEvent; language: Language }) {
  const glosses = useGlosses();
  const [english, setEnglish] = useState(glosses);
  useEffect(() => setEnglish(glosses), [glosses]); // the presenter's G key
  const [why, setWhy] = useState(false);
  // The reasons were written in the student's language when the payment was blocked.
  const translated = blocked.reasons.some((reason) => reason.text !== reason.text_en);
  // A panel written in English stays in English, whatever language is chosen afterwards.
  const shown: Language = english || !translated ? "en" : language;
  const advice = english ? blocked.advice_en : blocked.advice;
  const check = blocked.claim_check;

  return (
    <section
      aria-label="Payment blocked"
      className="overflow-hidden rounded-card border border-danger bg-surface motion-safe:animate-step-in"
    >
      <h3 className="flex items-center gap-2 bg-danger-tint px-4 py-2 font-heading text-18 font-semibold text-danger">
        <Ban aria-hidden className="size-5 shrink-0" />
        Payment blocked: no money was moved
      </h3>
      {check && (
        <div className="flex flex-col gap-2 px-4 py-3">
          <ClaimList claims={check.claims} shown={shown} />
          <Reasoning items={check.reasoning} shown={shown} />
        </div>
      )}
      <ul className={check ? "hidden" : "flex flex-col gap-2 px-4 py-3"}>
        {blocked.reasons.map((reason) => (
          <li key={reason.code} className="grid grid-cols-[auto_1fr] gap-x-2">
            <TriangleAlert aria-hidden className="mt-0.5 size-5 text-danger" strokeWidth={1.75} />
            <div lang={shown} className="min-w-0">
              <p className="text-15 font-medium text-ink">{english ? reason.title_en : reason.title}</p>
              {why && <p className="text-13 text-body">{english ? reason.text_en : reason.text}</p>}
              {reason.policy_clause &&
                (why ? (
                  <PolicyQuote clause={reason.policy_clause} shown={shown} />
                ) : (
                  <p className="truncate text-13 text-muted">
                    University policy: “{(reason.policy_clause.versions.en ?? reason.policy_clause).text}”
                  </p>
                ))}
            </div>
          </li>
        ))}
      </ul>
      <div className="border-t border-line px-4 py-2">
        <p lang={shown} className="text-13 font-medium text-ink">
          {why ? advice : (lead(advice) ?? advice)}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-1">
          {!check && (
            <Button variant="ghost" size="sm" aria-expanded={why} className="-ml-3" onClick={() => setWhy(!why)}>
              {why ? "Less" : "Why?"}
            </Button>
          )}
          {translated && (
            <Button variant="ghost" size="sm" className={check ? "-ml-3" : undefined} onClick={() => setEnglish(!english)}>
              {english ? `Show ${LANGUAGE_NAMES[language]}` : "Show English"}
            </Button>
          )}
          {blocked.audit_seq !== null && (
            <Link
              href={`/audit?entry=${blocked.audit_seq}`}
              className="ml-auto inline-flex items-center gap-1 rounded-sm text-13 font-medium text-teal hover:underline"
            >
              Audit log
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}
