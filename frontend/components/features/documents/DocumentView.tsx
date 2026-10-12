"use client";

import { BadgeCheck, CircleHelp, Languages, ShieldAlert, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { FIELD_LABELS, KIND_LABELS, STATUS, languageList } from "@/components/features/documents/labels";
import { PolicyQuote } from "@/components/features/documents/PolicyQuote";
import { SourceText } from "@/components/features/documents/SourceText";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { formatAmount, formatDate } from "@/lib/format";
import { LANGUAGE_NAMES, useLanguage } from "@/lib/language";
import type { Currency, DocumentDetail, DocumentField, Language, RiskSignal } from "@/lib/types";

/** "12000.00" -> 1200000, without floating point. */
function toMinor(decimal: string): number {
  const [whole, fraction = ""] = decimal.split(".");
  return Number(whole) * 100 + Number(fraction.padEnd(2, "0").slice(0, 2));
}

function displayValue(field: DocumentField, currency: string | undefined): string {
  if (field.name === "amount" && currency && /^\d+(\.\d{1,2})?$/.test(field.value)) {
    return formatAmount(toMinor(field.value), currency as Currency);
  }
  if (field.name === "due_date" && /^\d{4}-\d{2}-\d{2}$/.test(field.value)) return formatDate(field.value);
  return field.value;
}

function EnglishToggle({ shown, onToggle }: { shown: Language; onToggle: () => void }) {
  const { language } = useLanguage();
  if (!language || language === "en") return null;
  return (
    <Button variant="ghost" icon={Languages} onClick={onToggle}>
      {shown === "en" ? `Show ${LANGUAGE_NAMES[language]}` : "Show English"}
    </Button>
  );
}

function RiskPanel({ signals, shown, onToggle }: { signals: RiskSignal[]; shown: Language; onToggle: () => void }) {
  return (
    <section aria-label="Risk signals" className="rounded-card border border-amber-line bg-amber-tint p-6">
      <div className="flex items-center justify-between gap-4">
        <h3 className="flex items-center gap-2 font-heading text-18 font-semibold text-amber-ink">
          <TriangleAlert aria-hidden className="size-5" />
          Risk found
        </h3>
        <EnglishToggle shown={shown} onToggle={onToggle} />
      </div>
      <ul className="mt-3 flex flex-col gap-2">
        {signals.map((signal) => (
          <li key={signal.code} lang={shown}>
            <details>
              <summary className="flex cursor-pointer items-center justify-between gap-3 rounded-sm">
                <span className="text-15 font-semibold text-ink">{signal.title[shown]}</span>
                <span className="inline-flex items-center gap-1 text-13 font-medium text-amber-ink">
                  <CircleHelp aria-hidden className="size-4" />
                  Why?
                </span>
              </summary>
              <p className="mt-1 text-15 text-body">{signal.text[shown]}</p>
              <ul className="mt-1 flex flex-col gap-1 border-l-2 border-amber-line pl-3">
                {signal.evidence.map((quote) => (
                  <li key={quote} className="text-13 text-body">
                    {quote}
                  </li>
                ))}
              </ul>
              {signal.policy_clause && <PolicyQuote clause={signal.policy_clause} shown={shown} />}
            </details>
          </li>
        ))}
      </ul>
    </section>
  );
}

function FieldList({
  fields,
  onActive,
}: {
  fields: DocumentField[];
  onActive: (field: DocumentField | null) => void;
}) {
  const currency = fields.find((field) => field.name === "currency" && field.verified)?.value;
  return (
    <ul className="flex flex-col">
      {fields.map((field) => (
        <li key={field.name} className="border-t border-line first:border-t-0">
          <button
            type="button"
            onMouseEnter={() => onActive(field)}
            onMouseLeave={() => onActive(null)}
            onFocus={() => onActive(field)}
            onBlur={() => onActive(null)}
            className="flex w-full items-center justify-between gap-3 rounded-sm py-2 text-left transition-colors duration-150 hover:bg-teal-tint focus-visible:bg-teal-tint"
          >
            <span className="min-w-0">
              <span className="block text-13 text-muted">{FIELD_LABELS[field.name] ?? field.name}</span>
              <span className="block text-15 break-words text-ink">{displayValue(field, currency)}</span>
              {field.note && <span className="block text-13 text-amber-ink">{field.note}</span>}
            </span>
            {field.verified ? (
              <Badge tone="success" icon={BadgeCheck}>
                Verified
              </Badge>
            ) : (
              <Badge tone="warning">Unverified</Badge>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Everything Bridge read from one document: the text, the fields, the risks and the explanation. */
export function DocumentView({ document }: { document: DocumentDetail }) {
  const { language } = useLanguage();
  const [showEnglish, setShowEnglish] = useState(false);
  const [active, setActive] = useState<DocumentField | null>(null);

  const shown: Language = showEnglish ? "en" : (language ?? "en");
  const toggle = () => setShowEnglish(!showEnglish);
  const status = STATUS[document.status];

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="font-heading text-24 font-semibold break-words text-ink">{document.filename}</h2>
            <p className="mt-1 text-13 text-muted">
              {KIND_LABELS[document.kind]} · {languageList(document.languages)}
            </p>
          </div>
          <Badge tone={status.tone}>{status.label}</Badge>
        </div>
      </Card>

      {document.trust_flag === "untrusted" && (
        <section aria-label="Untrusted document" className="rounded-card border border-danger bg-danger-tint p-6">
          <h3 className="flex items-center gap-2 font-heading text-18 font-semibold text-danger">
            <ShieldAlert aria-hidden className="size-5" />
            Untrusted: hidden text found
          </h3>
          <p className="mt-1 text-15 text-body">Bridge ignored it and will not pay from this document.</p>
          {document.hidden_text.map((item) => (
            <blockquote
              key={item.text}
              className="mt-3 rounded-control border border-danger bg-surface p-3 text-13 break-words text-ink"
            >
              {item.text}
            </blockquote>
          ))}
        </section>
      )}

      {document.risk_signals.length > 0 && (
        <RiskPanel signals={document.risk_signals} shown={shown} onToggle={toggle} />
      )}

      <div className="grid grid-cols-2 gap-6">
        <Card title="Original text">
          <SourceText
            text={document.raw_text}
            active={active ? { start: active.start, end: active.end } : null}
            hidden={document.hidden_text.map((item) => item.text)}
          />
        </Card>
        <div className="flex flex-col gap-6">
          <Card title="Extracted fields">
            {document.fields.length === 0 ? (
              <p className="text-15 text-body">No payment details were found.</p>
            ) : (
              <FieldList fields={document.fields} onActive={setActive} />
            )}
          </Card>
          <Card>
            <div className="mb-2 flex items-center justify-between gap-4">
              <h2 className="font-heading text-18 font-semibold text-ink">Explanation</h2>
              <EnglishToggle shown={shown} onToggle={toggle} />
            </div>
            <p lang={shown} className="text-15 text-body">
              {document.explanation[shown]}
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
