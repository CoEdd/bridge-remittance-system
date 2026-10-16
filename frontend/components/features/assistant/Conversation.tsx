"use client";

import { LoaderCircle, MessageSquare, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useGlosses } from "@/lib/demo";
import { BlockedPanel } from "@/components/features/assistant/BlockedPanel";
import { DocumentCard } from "@/components/features/assistant/DocumentCard";
import { lead, type Turn } from "@/components/features/assistant/model";
import { PlanBlock } from "@/components/features/assistant/PlanBlock";
import { Steps } from "@/components/features/assistant/Steps";
import type { Problem } from "@/components/features/assistant/useAssistant";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import type { Action, AgentReply, Language, StepEvent } from "@/lib/types";

function UserMessage({ text }: { text: string }) {
  return (
    <p className="ml-auto max-w-[85%] rounded-card border border-line bg-surface px-4 py-2 text-15 break-words whitespace-pre-wrap text-ink">
      <span className="sr-only">You: </span>
      {text}
    </p>
  );
}

/** A reply from Bridge: its opening sentences, the rest behind "More", and the English behind a toggle. */
function AgentMessage({ reply }: { reply: AgentReply }) {
  const glosses = useGlosses();
  const [english, setEnglish] = useState(glosses);
  useEffect(() => setEnglish(glosses), [glosses]); // the presenter's G key
  const [expanded, setExpanded] = useState(false);
  const hasEnglish = reply.language !== "en" && reply.text_en !== reply.text;
  const opening = lead(reply.text);
  const openingEnglish = lead(reply.text_en);
  const long = opening !== null || (english && openingEnglish !== null);

  return (
    <div className="mr-auto max-w-[92%] rounded-card border border-line bg-teal-tint px-4 py-2 motion-safe:animate-step-in">
      <p className="text-13 font-semibold text-ink">Bridge</p>
      <p lang={reply.language} className="text-15 break-words whitespace-pre-wrap text-ink">
        {expanded ? reply.text : (opening ?? reply.text)}
      </p>
      {english && (
        <p lang="en" className="mt-1 border-t border-line pt-1 text-15 break-words whitespace-pre-wrap text-body">
          {expanded ? reply.text_en : (openingEnglish ?? reply.text_en)}
        </p>
      )}
      {(hasEnglish || long) && (
        <div className="-mb-1 -ml-3 flex flex-wrap items-center">
          {long && (
            <Button variant="ghost" size="sm" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
              {expanded ? "Less" : "More"}
            </Button>
          )}
          {hasEnglish && (
            <Button variant="ghost" size="sm" aria-pressed={english} onClick={() => setEnglish(!english)}>
              {english ? "Hide English" : "Show English"}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

function InlineProblem({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-3 rounded-card border border-line bg-surface px-4 py-2"
    >
      <p className="text-15 text-body">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" icon={RefreshCw} onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

interface TurnViewProps {
  turn: Turn;
  actions: Action[];
  language: Language;
  /** Set on the newest turn of this visit: runs it again if the agent could not finish it. */
  onRetry?: () => void;
}

/** One turn: what was asked, what the agent did, what it said, and what came of it. Each shown once. */
function TurnView({ turn, actions, language, onRetry }: TurnViewProps) {
  const steps = turn.events.flatMap((item): StepEvent[] => (item.event === "step" ? [item.data] : []));
  const failed = turn.events.find((item) => item.event === "error");
  return (
    <li className="flex flex-col gap-2">
      <UserMessage text={turn.userText} />
      <Steps steps={steps} actions={actions} />
      {steps.map((step) => step.tool === "read_document" && <DocumentCard key={step.id} step={step} />)}
      {failed?.event === "error" ? (
        <InlineProblem
          message={language === "en" ? failed.data.message_en : failed.data.message}
          onRetry={turn.state === "done" ? onRetry : undefined}
        />
      ) : (
        turn.reply && <AgentMessage reply={turn.reply} />
      )}
      {turn.events.map((item, index): ReactNode => {
        if (item.event === "blocked") return <BlockedPanel key={index} blocked={item.data} language={language} />;
        if (item.event === "approval_required") return <PlanBlock key={index} approval={item.data} actions={actions} />;
        return null;
      })}
    </li>
  );
}

interface ConversationProps {
  turns: Turn[];
  actions: Action[];
  language: Language;
  /** What Bridge is doing right now, or null when it is idle. */
  working: string | null;
  problem: Problem | null;
  retryLast: (() => void) | null;
  /** Shown while there is nothing to read yet. */
  emptyAction: ReactNode;
}

export function Conversation({ turns, actions, language, working, problem, retryLast, emptyAction }: ConversationProps) {
  const end = useRef<HTMLDivElement>(null);
  const eventCount = turns.reduce((count, turn) => count + turn.events.length + (turn.reply ? 1 : 0), 0);
  const closedCount = actions.filter((action) => action.closed_at !== null).length;
  const latestReply = [...turns].reverse().find((turn) => turn.reply)?.reply ?? null;

  // Keep the newest step, reply or receipt in view.
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [turns.length, eventCount, closedCount, working, problem]);

  return (
    // "relative" keeps the screen-reader-only labels inside this scrolling box. Without it they are
    // placed against the page and make the whole page scroll.
    <section className="relative flex-1 overflow-y-auto px-4 py-4" tabIndex={0} aria-label="Conversation">
      {turns.length === 0 && !working ? (
        <EmptyState icon={MessageSquare} message="There is no conversation yet." action={emptyAction} />
      ) : (
        <ol className="flex flex-col gap-6">
          {turns.map((turn, index) => (
            <TurnView
              key={turn.key}
              turn={turn}
              actions={actions}
              language={language}
              // Only a turn started in this visit, and only the newest one, can be run again.
              onRetry={index === turns.length - 1 && turn.key.startsWith("live-") ? (retryLast ?? undefined) : undefined}
            />
          ))}
        </ol>
      )}
      {working && (
        <p role="status" className="mt-4 flex items-center gap-2 text-13 text-muted">
          <LoaderCircle aria-hidden className="size-4 motion-safe:animate-spin" />
          Bridge is working · {working}
        </p>
      )}
      {problem && (
        <div className="mt-4">
          <InlineProblem message={problem.message} onRetry={problem.retry} />
        </div>
      )}
      {/* Screen readers hear each new reply once it is complete. */}
      <p aria-live="polite" className="sr-only">
        {latestReply && !working ? `Bridge: ${latestReply.text}` : ""}
      </p>
      <div ref={end} />
    </section>
  );
}
