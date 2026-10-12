"use client";

import { useRef, useState } from "react";
import { ApprovalSheet } from "@/components/features/assistant/ApprovalSheet";
import { Composer } from "@/components/features/assistant/Composer";
import { ContextPanel } from "@/components/features/assistant/ContextPanel";
import { Conversation } from "@/components/features/assistant/Conversation";
import { suggestNext, type Suggestion } from "@/components/features/assistant/model";
import { SuggestedNext } from "@/components/features/assistant/SuggestedNext";
import { useAssistant } from "@/components/features/assistant/useAssistant";
import { PasteSheet } from "@/components/features/documents/PasteSheet";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { useLanguage } from "@/lib/language";

// Three columns from 1400px wide; below that the suggestions sit in a row above the conversation.
// The height is the window minus the header (6rem and its 1px border) and the page padding (4rem).
const LAYOUT =
  "grid h-[calc(100vh-10rem-1px)] min-h-[480px] gap-x-6 gap-y-4 " +
  "grid-cols-[minmax(0,1fr)_320px] grid-rows-[auto_minmax(0,1fr)] [grid-template-areas:'next_context'_'chat_context'] " +
  "min-[1400px]:grid-cols-[260px_minmax(0,1fr)_360px] min-[1400px]:grid-rows-[minmax(0,1fr)] min-[1400px]:[grid-template-areas:'next_chat_context']";

/** The Assistant screen: suggestions, the conversation with Bridge, and the facts behind it. */
export function Assistant() {
  const assistant = useAssistant();
  const { language } = useLanguage();
  const fileInput = useRef<HTMLInputElement>(null);
  const [pasting, setPasting] = useState(false);
  const [readingPaste, setReadingPaste] = useState(false);
  const { initial, loaded, live, working } = assistant;

  if (initial.state.status === "error") {
    return (
      <Card>
        <ErrorState message={initial.state.message} onRetry={initial.reload} />
      </Card>
    );
  }
  if (!loaded || !live || !language) {
    return (
      <div role="status" className={LAYOUT}>
        <Skeleton className="h-24 w-full [grid-area:next]" />
        <Skeleton className="h-full w-full [grid-area:chat]" />
        <Skeleton className="h-full w-full [grid-area:context]" />
        <span className="sr-only">Loading the assistant</span>
      </div>
    );
  }

  const busy = working !== null;
  const suggestions = suggestNext({ ...live, demos: loaded.demos, language });

  function useDemo(key: string) {
    // The stranger's transfer is an event: the money arrives first, then the message.
    if (key === "stranger") void assistant.share(async () => (await api.strangerTransfer()).document);
    else void assistant.share(() => api.ingestDemoDocument(key));
  }

  function pick(suggestion: Suggestion) {
    if (suggestion.kind === "upload") fileInput.current?.click();
    if (suggestion.kind === "demo") useDemo(suggestion.demoKey === "mule_message" ? "stranger" : suggestion.demoKey);
    if (suggestion.kind === "ask") assistant.ask(suggestion.label);
    if (suggestion.kind === "approve") assistant.setOpenPlan(suggestion.planId);
  }

  async function readPaste(text: string): Promise<boolean> {
    setReadingPaste(true);
    const started = await assistant.share(() => api.pasteMessage(text));
    setReadingPaste(false);
    if (started) setPasting(false);
    return started;
  }

  return (
    <div className={LAYOUT}>
      <div className="[grid-area:next]">
        <SuggestedNext suggestions={suggestions} disabled={busy} onPick={pick} />
      </div>

      <div className="flex min-h-0 flex-col rounded-card border border-line bg-surface [grid-area:chat]">
        <Conversation
          turns={assistant.turns}
          actions={live.actions}
          language={language}
          working={working}
          problem={assistant.problem}
          retryLast={assistant.retryLast}
          onOpenPlan={assistant.setOpenPlan}
          emptyAction={<Button onClick={() => useDemo("tuition_invoice")}>Use demo: tuition invoice</Button>}
        />
        <Composer
          disabled={busy}
          onSend={assistant.ask}
          onUpload={(file) => void assistant.share(() => api.uploadDocument(file))}
          onPaste={() => setPasting(true)}
          demoItems={loaded.demos.map((demo) => ({ key: demo.key, label: demo.label, hint: demo.filename }))}
          onDemo={useDemo}
          fileInput={fileInput}
        />
      </div>

      <div className="flex min-h-0 flex-col [grid-area:context]">
        <ContextPanel live={live} language={language} onOpenPlan={assistant.setOpenPlan} />
      </div>

      <PasteSheet open={pasting} onClose={() => setPasting(false)} busy={readingPaste} onRead={readPaste} />
      <ApprovalSheet
        planId={assistant.openPlan}
        actions={live.actions}
        payees={live.payees}
        settings={loaded.settings}
        me={loaded.me}
        language={language}
        onApprove={assistant.approve}
        onCancel={assistant.cancel}
        onClose={() => assistant.setOpenPlan(null)}
      />
    </div>
  );
}
