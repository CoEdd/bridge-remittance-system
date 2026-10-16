"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

/**
 * The presenter's demo mode: whether the demo bar shows, whether English glosses show
 * everywhere, and a small command registry. A page registers what it can do (the
 * Assistant can "ask", the audit log can "verify and tamper"), and the demo bar calls
 * those commands, so every step runs through the same screens a person would use.
 */

type Handler = (argument?: string) => Promise<void> | void;

interface DemoState {
  visible: boolean;
  toggleVisible: () => void;
  /** English under every reply, panel and explanation (key G). */
  glosses: boolean;
  toggleGlosses: () => void;
  register: (name: string, handler: Handler) => () => void;
  /** Runs a page's command, waiting up to `timeoutMs` for the page to mount and register it. */
  command: (name: string, argument?: string, timeoutMs?: number) => Promise<void>;
}

const DemoContext = createContext<DemoState | null>(null);
const VISIBLE_KEY = "bridge.demoBar";

export function DemoProvider({ children }: { children: ReactNode }) {
  const [visible, setVisible] = useState(false);
  const [glosses, setGlosses] = useState(false);
  const handlers = useRef(new Map<string, Handler>());

  // The bar remembers whether it was open, in this browser only.
  useEffect(() => {
    try {
      setVisible(window.localStorage.getItem(VISIBLE_KEY) === "1");
    } catch {
      // Storage blocked: start hidden.
    }
  }, []);
  const toggleVisible = useCallback(() => {
    setVisible((now) => {
      try {
        window.localStorage.setItem(VISIBLE_KEY, now ? "0" : "1");
      } catch {
        // Storage blocked: the choice lasts until the page reloads.
      }
      return !now;
    });
  }, []);
  const toggleGlosses = useCallback(() => setGlosses((now) => !now), []);

  const register = useCallback((name: string, handler: Handler) => {
    handlers.current.set(name, handler);
    return () => {
      if (handlers.current.get(name) === handler) handlers.current.delete(name);
    };
  }, []);

  const command = useCallback(async (name: string, argument?: string, timeoutMs = 15000) => {
    const started = Date.now();
    while (!handlers.current.has(name)) {
      if (Date.now() - started > timeoutMs) throw new Error(`The screen for "${name}" did not open.`);
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    await handlers.current.get(name)?.(argument);
  }, []);

  const value = useMemo(
    () => ({ visible, toggleVisible, glosses, toggleGlosses, register, command }),
    [visible, toggleVisible, glosses, toggleGlosses, register, command],
  );
  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>;
}

export function useDemo(): DemoState {
  const value = useContext(DemoContext);
  if (!value) throw new Error("useDemo needs a DemoProvider");
  return value;
}

/** Whether English glosses are on. Safe outside the provider (the style guide). */
export function useGlosses(): boolean {
  return useContext(DemoContext)?.glosses ?? false;
}

/** Registers page commands for the demo bar while the page is mounted. Handlers may change on every render. */
export function useDemoCommands(commands: Record<string, Handler>): void {
  const demo = useContext(DemoContext);
  const latest = useRef(commands);
  useEffect(() => {
    latest.current = commands;
  });
  const names = Object.keys(commands).join(",");
  useEffect(() => {
    if (!demo) return;
    const undo = names
      .split(",")
      .filter(Boolean)
      .map((name) => demo.register(name, (argument) => latest.current[name]?.(argument)));
    return () => undo.forEach((stop) => stop());
  }, [demo, names]);
}
