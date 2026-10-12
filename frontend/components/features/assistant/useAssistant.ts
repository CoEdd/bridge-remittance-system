"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { isWaiting, turnsFromHistory, type Turn } from "@/components/features/assistant/model";
import { ApiError, api } from "@/lib/api";
import { followTurn } from "@/lib/chat";
import { useLanguage } from "@/lib/language";
import type {
  Accounts,
  Action,
  Bill,
  ChatMessage,
  DemoDocument,
  DemoSettings,
  DocumentSummary,
  Payee,
  Transaction,
  User,
} from "@/lib/types";
import { useApi } from "@/lib/useApi";

/** What changes as the student acts: read again after every turn and every approval. */
export interface Live {
  accounts: Accounts;
  bills: Bill[];
  actions: Action[];
  documents: DocumentSummary[];
  payees: Payee[];
  /** The newest transfer received from someone else, if any. */
  received: Transaction | null;
}

interface Loaded {
  history: ChatMessage[];
  live: Live;
  settings: DemoSettings;
  demos: DemoDocument[];
  me: User;
}

async function loadLive(signal?: AbortSignal): Promise<Live> {
  const [accounts, bills, actions, documents, payees, received] = await Promise.all([
    api.accounts(signal),
    api.bills(signal),
    api.actions(signal),
    api.documents(signal),
    api.payees(signal),
    api.transactions({ category: "transfer_in", limit: 1 }, signal),
  ]);
  return { accounts, bills, actions, documents, payees, received: received[0] ?? null };
}

async function loadEverything(signal: AbortSignal): Promise<Loaded> {
  const [history, live, settings, demos, me] = await Promise.all([
    api.chatHistory(signal),
    loadLive(signal),
    api.demoSettings(signal),
    api.demoDocuments(signal),
    api.me(signal),
  ]);
  return { history, live, settings, demos, me };
}

export type ApproveResult =
  | { kind: "ok" }
  | { kind: "wrong_code"; attemptsLeft: number }
  | { kind: "failed"; message: string };

export interface Problem {
  message: string;
  retry: () => void;
}

// The scripted agent answers within milliseconds. Its events are shown one at a time,
// this far apart, so each step can be seen as it happens.
const STEP_GAP_MS = 350;

/** Runs tasks in order with a short gap between them. Returns the adder and a way to drop what is left. */
function paced(gapMs: number): { add: (task: () => void) => void; stop: () => void } {
  const queue: (() => void)[] = [];
  let timer: ReturnType<typeof setTimeout> | null = null;
  function next() {
    const task = queue.shift();
    if (!task) {
      timer = null;
      return;
    }
    task();
    timer = setTimeout(next, gapMs);
  }
  return {
    add(task) {
      queue.push(task);
      if (timer === null) next();
    },
    stop() {
      queue.length = 0;
      if (timer !== null) clearTimeout(timer);
    },
  };
}

function messageOf(failure: unknown, fallback: string): string {
  return failure instanceof ApiError ? failure.message : fallback;
}

/** Everything the Assistant screen shows and does. The backend holds the state; this reads and follows it. */
export function useAssistant() {
  const initial = useApi(loadEverything);
  const { whenSaved } = useLanguage();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [live, setLive] = useState<Live | null>(null);
  /** Set while the agent is working: the line shown under the conversation. */
  const [working, setWorking] = useState<string | null>(null);
  const [problem, setProblem] = useState<Problem | null>(null);
  /** Runs the newest turn of this visit again, for "Try again" on a turn the agent could not finish. */
  const [retryLast, setRetryLast] = useState<(() => void) | null>(null);
  const [openPlan, setOpenPlan] = useState<string | null>(null);
  const stopFollowing = useRef<(() => void) | null>(null);
  const liveCount = useRef(0);

  const loaded = initial.state.status === "ready" ? initial.state.data : null;
  useEffect(() => {
    if (!loaded) return;
    setTurns(turnsFromHistory(loaded.history));
    setLive(loaded.live);
  }, [loaded]);

  useEffect(() => () => stopFollowing.current?.(), []);

  const refresh = useCallback(async () => {
    try {
      setLive(await loadLive());
    } catch {
      // Keep what is on screen; the next refresh will catch up.
    }
  }, []);

  const follow = useCallback(
    (streamId: string, userText: string, retry: () => void) => {
      liveCount.current += 1;
      const key = `live-${liveCount.current}`;
      const change = (update: (turn: Turn) => Turn) =>
        setTurns((all) => all.map((turn) => (turn.key === key ? update(turn) : turn)));

      setTurns((all) => [...all, { key, userText, events: [], reply: null, state: "streaming" }]);
      setRetryLast(() => retry);
      const show = paced(STEP_GAP_MS);
      const stopStream = followTurn(streamId, {
        onEvent: (event) =>
          show.add(() => {
            change((turn) => ({ ...turn, events: [...turn.events, event] }));
            if (event.event === "step") setWorking(event.data.label);
            // The approval sheet opens by itself, once the actions it shows have been read.
            if (event.event === "approval_required") void refresh().then(() => setOpenPlan(event.data.plan_id));
          }),
        onReply: (reply) => show.add(() => change((turn) => ({ ...turn, reply }))),
        onDone: () =>
          show.add(() => {
            change((turn) => ({ ...turn, state: "done" }));
            setWorking(null);
            void refresh();
          }),
        onLost: () =>
          show.add(() => {
            change((turn) => ({ ...turn, state: "lost" }));
            setWorking(null);
            setProblem({ message: "The connection to Bridge was lost.", retry });
            void refresh();
          }),
      });
      stopFollowing.current = () => {
        stopStream();
        show.stop();
      };
    },
    [refresh],
  );

  /** Send a typed or suggested question. */
  const ask = useCallback(
    function send(text: string) {
      setProblem(null);
      setWorking("Reading your message");
      // A language chosen a moment ago must reach the backend first, so this reply uses it.
      whenSaved()
        .then(() => api.sendChat(text))
        .then((turn) => follow(turn.stream_id, turn.text, () => send(text)))
        .catch((failure: unknown) => {
          setWorking(null);
          setProblem({ message: messageOf(failure, "The message could not be sent."), retry: () => send(text) });
        });
    },
    [follow, whenSaved],
  );

  /** Take in a document (an upload, a pasted message or a demo file), then let the agent read and explain it. */
  const share = useCallback(
    async (takeIn: () => Promise<DocumentSummary>): Promise<boolean> => {
      // Kept across retries, so a document that was taken in is not taken in twice.
      let taken: DocumentSummary | null = null;
      async function attempt(): Promise<boolean> {
        setProblem(null);
        setWorking("Reading the document");
        try {
          taken ??= await takeIn();
          const shared = taken;
          await Promise.all([whenSaved(), refresh()]);
          const turn = await api.chatAboutDocument(shared.id);
          follow(turn.stream_id, turn.text, () => void attempt());
          return true;
        } catch (failure) {
          setWorking(null);
          setProblem({
            message: messageOf(failure, "The document could not be read."),
            retry: () => void attempt(),
          });
          return false;
        }
      }
      return attempt();
    },
    [follow, refresh, whenSaved],
  );

  /** Confirm an action and, for Tier 3, enter its one-time code. */
  const approve = useCallback(
    async (action: Action, code: string): Promise<ApproveResult> => {
      try {
        let current = action;
        if (current.status === "awaiting_confirm") current = await api.confirmAction(current.id);
        if (current.status === "awaiting_otp") {
          const result = await api.submitOtp(current.id, code);
          if (!result.accepted) return { kind: "wrong_code", attemptsLeft: result.attempts_left };
        }
        return { kind: "ok" };
      } catch (failure) {
        return { kind: "failed", message: messageOf(failure, "The action could not be approved.") };
      } finally {
        await refresh();
      }
    },
    [refresh],
  );

  /** Cancel an action and the later steps of its plan, which depend on it. */
  const cancel = useCallback(
    async (action: Action): Promise<string | null> => {
      try {
        const rest = (await api.actions()).filter(
          (item) => item.plan_id === action.plan_id && item.id >= action.id && isWaiting(item),
        );
        for (const item of rest) await api.cancelAction(item.id);
        return null;
      } catch (failure) {
        return messageOf(failure, "The action could not be cancelled.");
      } finally {
        await refresh();
      }
    },
    [refresh],
  );

  // A payment in its cooling-off wait runs by itself on the backend: watch for it.
  const coolingOff = live?.actions.some((action) => action.status === "cooling_off") ?? false;
  useEffect(() => {
    if (!coolingOff) return;
    const timer = setInterval(() => void refresh(), 1000);
    return () => clearInterval(timer);
  }, [coolingOff, refresh]);

  // The sheet closes by itself once every step of its plan has run.
  useEffect(() => {
    if (!openPlan || !live) return;
    const plan = live.actions.filter((action) => action.plan_id === openPlan);
    if (plan.length > 0 && plan.every((action) => action.status === "executed")) setOpenPlan(null);
  }, [openPlan, live]);

  return {
    initial,
    loaded,
    turns,
    live,
    working,
    problem,
    retryLast,
    openPlan,
    setOpenPlan,
    ask,
    share,
    approve,
    cancel,
  };
}

export type Assistant = ReturnType<typeof useAssistant>;
