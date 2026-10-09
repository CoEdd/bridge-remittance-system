"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import type { Language } from "./types";
import { useApi } from "./useApi";

export const LANGUAGE_NAMES: Record<Language, string> = {
  ms: "Bahasa Melayu",
  en: "English",
  zh: "中文",
};

interface LanguageState {
  /** The student's preferred language; null until it has loaded from GET /me. */
  language: Language | null;
  /** Save a new choice with PATCH /me. */
  choose: (language: Language) => void;
  saveFailed: boolean;
}

const LanguageContext = createContext<LanguageState>({ language: null, choose: () => {}, saveFailed: false });

/** Shares the preferred language between the header switcher and the pages. */
export function LanguageProvider({ children }: { children: ReactNode }) {
  const { state } = useApi(api.me);
  const [chosen, setChosen] = useState<Language | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);

  const saved = state.status === "ready" ? state.data.preferred_language : null;
  const language = chosen ?? saved;

  const choose = useCallback(
    (next: Language) => {
      const previous = language;
      setChosen(next);
      setSaveFailed(false);
      api.updateLanguage(next).catch(() => {
        setChosen(previous);
        setSaveFailed(true);
      });
    },
    [language],
  );

  const value = useMemo(() => ({ language, choose, saveFailed }), [language, choose, saveFailed]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageState {
  return useContext(LanguageContext);
}
