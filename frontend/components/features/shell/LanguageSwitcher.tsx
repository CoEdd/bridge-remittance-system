"use client";

import { Check, Languages } from "lucide-react";
import { useId } from "react";
import { LANGUAGE_NAMES, useLanguage } from "@/lib/language";
import type { Language } from "@/lib/types";

const ORDER: Language[] = ["ms", "en", "zh"];

/**
 * The student's preferred language. Read from GET /me and saved with PATCH /me.
 * Risk reasons and document explanations are shown in this language.
 */
export function LanguageSwitcher() {
  const labelId = useId();
  const { language, choose, saveFailed } = useLanguage();

  return (
    <div className="flex items-center gap-2">
      {saveFailed && (
        <span role="alert" className="text-13 font-medium text-danger">
          Not saved. Choose again.
        </span>
      )}
      <span id={labelId} className="flex items-center gap-1 text-13 text-muted">
        <Languages aria-hidden className="size-4" />
        Language
      </span>
      <div
        role="radiogroup"
        aria-labelledby={labelId}
        className="flex h-10 items-center gap-1 rounded-control border border-line bg-surface p-1"
      >
        {ORDER.map((code) => (
          <label key={code} className="cursor-pointer">
            <input
              type="radio"
              name="language"
              value={code}
              checked={language === code}
              disabled={language === null}
              onChange={() => choose(code)}
              className="peer sr-only"
            />
            <span
              lang={code}
              className="flex h-7.5 items-center gap-1 rounded-sm border border-transparent px-2 text-13 text-body transition-colors duration-150 peer-checked:border-teal peer-checked:bg-teal-tint peer-checked:font-semibold peer-checked:text-ink peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-teal peer-disabled:cursor-not-allowed peer-disabled:text-muted"
            >
              {language === code && <Check aria-hidden className="size-3.5 text-teal" />}
              {LANGUAGE_NAMES[code]}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}
