"use client";

import { Check, Languages } from "lucide-react";
import { useId, useState } from "react";

const LANGUAGES = [
  { code: "ms", label: "Bahasa Melayu" },
  { code: "en", label: "English" },
  { code: "zh", label: "中文" },
] as const;

type LanguageCode = (typeof LANGUAGES)[number]["code"];

/**
 * Language choice for Bridge's replies. Not wired yet: it only remembers the
 * selection on this page. Ahmad's preferred language is the default.
 */
export function LanguageSwitcher() {
  const labelId = useId();
  const [selected, setSelected] = useState<LanguageCode>("ms");

  return (
    <div className="flex items-center gap-2">
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
              onChange={() => setSelected(code)}
              className="peer sr-only"
            />
            <span
              lang={code}
              className="flex h-[30px] items-center gap-1 rounded-sm border border-transparent px-2 text-13 text-body transition-colors duration-150 peer-checked:border-teal peer-checked:bg-teal-tint peer-checked:font-semibold peer-checked:text-ink peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-teal"
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
