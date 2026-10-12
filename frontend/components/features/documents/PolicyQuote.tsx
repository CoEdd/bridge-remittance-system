import { LANGUAGE_LABELS } from "@/components/features/documents/labels";
import type { Language, PolicyClause } from "@/lib/types";

/**
 * The institution's own policy clause, quoted with its source file and language.
 * The policy is published in English and Chinese: a Chinese reader gets the Chinese
 * file and everyone else the English one.
 */
export function PolicyQuote({ clause, shown }: { clause: PolicyClause; shown: Language }) {
  const language: Language = shown === "zh" && clause.versions.zh ? "zh" : clause.versions.en ? "en" : clause.language;
  const version = clause.versions[language] ?? clause;
  return (
    <figure className="mt-3 rounded-control border border-line bg-surface p-4">
      <figcaption className="text-13 font-medium text-muted">University payment policy</figcaption>
      <blockquote lang={language} className="mt-1 text-15 text-ink">
        {version.text}
      </blockquote>
      <p className="mt-2 text-13 text-muted">
        Source: {version.file} · {LANGUAGE_LABELS[language]}
      </p>
    </figure>
  );
}
