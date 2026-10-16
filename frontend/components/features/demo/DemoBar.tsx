"use client";

import clsx from "clsx";
import { Check, Play, RotateCcw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { DEMO_STEPS, type DemoStep } from "@/components/features/demo/steps";
import { Button } from "@/components/ui/Button";
import { api, ApiError } from "@/lib/api";
import { useDemo } from "@/lib/demo";
import type { DemoStateData, DemoStepKey } from "@/lib/types";

const POLL_MS = 1500;
const FLASH_MS = 600;

/** Briefly outlines the panel a finished step is about, so the audience knows where to look. */
function flash(selector: string) {
  window.setTimeout(() => {
    const target = [...document.querySelectorAll<HTMLElement>(selector)].at(-1);
    if (!target) return;
    target.classList.remove("demo-flash");
    void target.offsetWidth; // restart the animation if it is already running
    target.classList.add("demo-flash");
    window.setTimeout(() => target.classList.remove("demo-flash"), FLASH_MS);
  }, 250);
}

function typing(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
}

/**
 * The presenter's demo bar: the nine steps, a caption to read out, "Run step" and "Reset demo".
 * Every step runs through the real screens and API; approving a payment is always left to
 * the presenter. Progress comes from GET /demo/state, so steps done by hand count too.
 */
export function DemoBar() {
  const demo = useDemo();
  const router = useRouter();
  const [state, setState] = useState<DemoStateData | null>(null);
  const [cursor, setCursor] = useState(0);
  const [running, setRunning] = useState<DemoStepKey | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  // After Left arrow the cursor stays where the presenter put it, instead of following progress.
  const pinned = useRef(false);
  // Right arrow pressed while a step was still finishing: acted on once it is done.
  const queued = useRef(false);
  const doneBefore = useRef<Set<DemoStepKey> | null>(null);

  const refresh = useCallback(async () => {
    try {
      setState(await api.demoState());
    } catch {
      // The backend is restarting or busy: keep the last state; the next poll catches up.
    }
  }, []);

  useEffect(() => {
    if (!demo.visible) return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [demo.visible, refresh]);

  const isDone = useCallback(
    (key: DemoStepKey) => state?.steps.find((step) => step.key === key)?.done ?? false,
    [state],
  );
  const firstOpen = DEMO_STEPS.findIndex((step) => !isDone(step.key));
  const frontier = firstOpen === -1 ? DEMO_STEPS.length - 1 : firstOpen;

  // Follow progress: outline what just finished, and move on to the next open step.
  useEffect(() => {
    if (!state) return;
    const now = new Set(state.steps.filter((step) => step.done).map((step) => step.key));
    if (doneBefore.current) {
      for (const step of DEMO_STEPS) if (now.has(step.key) && !doneBefore.current.has(step.key)) flash(step.flash);
    }
    doneBefore.current = now;
    if (!pinned.current) setCursor(frontier);
  }, [state, frontier]);

  // The page below must not slide under the bar: tell the layout how tall it is.
  useEffect(() => {
    const element = root.current;
    const set = (height: number) => document.documentElement.style.setProperty("--demo-bar", `${height}px`);
    if (!demo.visible || !element) {
      set(0);
      return;
    }
    const observer = new ResizeObserver(() => set(element.offsetHeight));
    observer.observe(element);
    return () => {
      observer.disconnect();
      set(0);
    };
  }, [demo.visible]);

  // Focused at once: the presenter pressed R, and Enter confirms.
  useEffect(() => {
    if (confirming) root.current?.querySelector<HTMLButtonElement>("[data-confirm-reset]")?.focus();
  }, [confirming]);

  const show = useCallback(
    (step: DemoStep) => {
      const path = step.path(state?.invoice_document_id ?? null);
      if (`${window.location.pathname}${window.location.search}` !== path) router.push(path);
    },
    [router, state],
  );

  const runners: Record<DemoStepKey, () => Promise<void>> = {
    upload: async () => {
      router.push("/assistant");
      await demo.command("assistant:share", "tuition_invoice");
    },
    verify: async () => {
      router.push("/assistant");
      await demo.command("assistant:idle");
      const now = await api.demoState();
      if (now.invoice_document_id !== null) router.push(`/documents?id=${now.invoice_document_id}`);
    },
    plan: async () => {
      router.push("/assistant");
      await demo.command("assistant:ask", "deadline");
    },
    pay: async () => {
      router.push("/assistant");
      const now = await api.demoState();
      await demo.command("assistant:openPlan", now.pending_plan_id ?? undefined);
    },
    agent: async () => {
      router.push("/assistant");
      await demo.command("assistant:paste", "agent_offer");
      await demo.command("assistant:idle");
      await demo.command("assistant:ask", "agent");
      await demo.command("assistant:idle");
      await demo.command("assistant:reasoning");
    },
    mule: async () => {
      router.push("/assistant");
      await demo.command("assistant:stranger");
      await demo.command("assistant:idle");
      await demo.command("assistant:ask", "forward");
      await demo.command("assistant:idle");
    },
    audit: async () => {
      router.push("/audit");
      await demo.command("audit:proof");
    },
    redteam: async () => {
      router.push("/security");
      await demo.command("security:run");
    },
    sources: async () => {
      router.push("/sources");
    },
  };

  async function run(index: number) {
    const step = DEMO_STEPS[index];
    if (!step || running) return;
    setCursor(index);
    setRunning(step.key);
    setProblem(null);
    let failed = false;
    try {
      await runners[step.key]();
    } catch (failure) {
      failed = true;
      setProblem(failure instanceof ApiError || failure instanceof Error ? failure.message : "The step could not run.");
    } finally {
      setRunning(null);
      void refresh();
    }
    if (queued.current) {
      queued.current = false;
      if (!failed) void next();
    }
  }

  /**
   * Right arrow: run the step under the cursor, or move on to the next one if it is done.
   * Progress is read fresh first, so a quick press never runs a finished step again.
   */
  async function next() {
    if (running) {
      queued.current = true;
      return;
    }
    let latest = state;
    try {
      latest = await api.demoState();
      setState(latest);
    } catch {
      // Use what the last poll said.
    }
    const finished = (key: DemoStepKey) => latest?.steps.find((step) => step.key === key)?.done ?? false;
    const open = DEMO_STEPS.findIndex((step) => !finished(step.key));
    const edge = open === -1 ? DEMO_STEPS.length - 1 : open;
    const from = pinned.current ? cursor : edge;
    if (!finished(DEMO_STEPS[from].key)) return void run(from);
    const target = Math.min(from + 1, DEMO_STEPS.length - 1);
    pinned.current = target < edge;
    setCursor(target);
    if (finished(DEMO_STEPS[target].key)) show(DEMO_STEPS[target]);
    else void run(target);
  }

  /** Left arrow: go back one step. Navigation only; nothing is undone. */
  function back() {
    const target = Math.max(cursor - 1, 0);
    pinned.current = target < frontier;
    setCursor(target);
    show(DEMO_STEPS[target]);
  }

  function jump(index: number) {
    pinned.current = index < frontier;
    setCursor(index);
    show(DEMO_STEPS[index]);
  }

  async function reset() {
    setResetting(true);
    setProblem(null);
    try {
      await api.resetDemo();
      // A full load of Home: the chat, the wallets and the chosen language all start again.
      window.location.assign("/");
    } catch (failure) {
      setProblem(failure instanceof ApiError ? failure.message : "The demo could not be reset.");
      setResetting(false);
      setConfirming(false);
    }
  }

  // Presenter keys. Never while typing, and never while a dialog (the approval sheet) is open.
  const keys = useRef<(event: KeyboardEvent) => void>(() => undefined);
  useEffect(() => {
    keys.current = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey || event.repeat || typing(event.target)) return;
      if (document.querySelector("[role='dialog']")) return;
      const key = event.key.toLowerCase();
      if (key === "d") {
        event.preventDefault();
        demo.toggleVisible();
        return;
      }
      if (!demo.visible) return;
      if (confirming) {
        if (key === "escape") setConfirming(false);
        return;
      }
      if (key === "arrowright") void next();
      else if (key === "arrowleft") back();
      else if (key === "r") setConfirming(true);
      else if (key === "g") demo.toggleGlosses();
      else return;
      event.preventDefault();
    };
  });
  useEffect(() => {
    const listener = (event: KeyboardEvent) => keys.current(event);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);

  if (!demo.visible) return null;
  const current = DEMO_STEPS[cursor];

  return (
    <div ref={root} role="region" aria-label="Demo bar" className="border-t border-line bg-paper px-8 py-2">
      <div className="flex items-center gap-4">
        <ol className="flex min-w-0 flex-1 items-center gap-1" aria-label="Demo steps">
          {DEMO_STEPS.map((step, index) => {
            const done = isDone(step.key);
            const here = index === cursor;
            return (
              <li key={step.key}>
                <button
                  type="button"
                  onClick={() => jump(index)}
                  aria-current={here ? "step" : undefined}
                  title={step.label}
                  className={clsx(
                    "flex h-7 items-center gap-1 rounded-full border px-2 text-13 whitespace-nowrap transition-colors duration-150",
                    here ? "border-teal bg-teal-tint font-medium text-ink" : "border-line bg-surface text-body hover:border-muted",
                  )}
                >
                  {done ? <Check aria-hidden className="size-3.5 text-teal" /> : null}
                  <span className="tabular-nums">{index + 1}</span>
                  <span className={here ? undefined : "sr-only min-[1600px]:not-sr-only"}>{step.label}</span>
                  {done && <span className={here ? "text-muted" : undefined}>Done</span>}
                </button>
              </li>
            );
          })}
        </ol>
        {confirming ? (
          <div className="flex items-center gap-2" role="group" aria-label="Reset the demo?">
            <span className="text-13 font-medium text-ink">Reset the demo?</span>
            <Button data-confirm-reset size="sm" variant="danger" loading={resetting} onClick={() => void reset()}>
              Reset
            </Button>
            <Button size="sm" variant="ghost" disabled={resetting} onClick={() => setConfirming(false)}>
              Keep
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <Button size="sm" icon={Play} loading={running !== null} onClick={() => void next()}>
              {isDone(current.key) && cursor < DEMO_STEPS.length - 1 ? "Next step" : "Run step"}
            </Button>
            <Button size="sm" variant="ghost" icon={RotateCcw} onClick={() => setConfirming(true)}>
              Reset demo
            </Button>
          </div>
        )}
      </div>
      <div className="mt-1 flex items-center gap-4">
        <p className="min-w-0 flex-1 truncate text-15 font-medium text-ink" aria-live="polite">
          <span className="mr-2 text-muted tabular-nums">{cursor + 1}.</span>
          {current.caption}
        </p>
        {problem && (
          <p role="alert" className="text-13 font-medium text-danger">
            {problem}
          </p>
        )}
        <p className="shrink-0 text-13 text-muted">
          <span className="min-[1400px]:hidden">Keys: Right arrow · R · G · D</span>
          <span className="hidden min-[1400px]:inline">
            Presenter keys: Right arrow next · R reset · G English · D hide
          </span>
        </p>
      </div>
    </div>
  );
}
