"use client";

import { Check, Languages } from "lucide-react";
import { useId, useState } from "react";
import { api } from "@/lib/api";
import type { Language } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const LANGUAGES: { code: Language; label: string }[] = [
  { code: "ms", label: "Bahasa Melayu" },
  { code: "en", label: "English" },
  { code: "zh", label: "中文" },
];

/**
 * The student's preferred language. Read from GET /me and saved with PATCH /me.
 * It is stored now; Bridge's replies start using it in a later step.
 */
export function LanguageSwitcher() {
  const labelId = useId();
  const { state } = useApi(api.me);
  const [chosen, setChosen] = useState<Language | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);

  const saved = state.status === "ready" ? state.data.preferred_language : null;
  const selected = chosen ?? saved;

  async function choose(code: Language) {
    const previous = selected;
    setChosen(code);
    setSaveFailed(false);
    try {
      await api.updateLanguage(code);
    } catch {
      setChosen(previous);
      setSaveFailed(true);
    }
  }

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
        {LANGUAGES.map(({ code, label }) => (
          <label key={code} className="cursor-pointer">
            <input
              type="radio"
              name="language"
              value={code}
              checked={selected === code}
              disabled={saved === null}
              onChange={() => void choose(code)}
              className="peer sr-only"
            />
            <span
              lang={code}
              className="flex h-7.5 items-center gap-1 rounded-sm border border-transparent px-2 text-13 text-body transition-colors duration-150 peer-checked:border-teal peer-checked:bg-teal-tint peer-checked:font-semibold peer-checked:text-ink peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-teal peer-disabled:cursor-not-allowed peer-disabled:text-muted"
            >
              {selected === code && <Check aria-hidden className="size-3.5 text-teal" />}
              {label}
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}
