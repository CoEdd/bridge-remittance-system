"use client";

import { BadgeCheck, Languages, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { CountdownRing } from "@/components/features/assistant/CountdownRing";
import { costRows } from "@/components/features/assistant/details";
import { describeAction, isWaiting } from "@/components/features/assistant/model";
import { Rows, tierOf } from "@/components/features/assistant/StepCard";
import type { ApproveResult } from "@/components/features/assistant/useAssistant";
import { Badge, TierBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import { formatAmount, formatDate } from "@/lib/format";
import type { Action, DemoSettings, Language, Payee, User } from "@/lib/types";

const CODE_LENGTH = 6;

const SOURCES: Record<NonNullable<Payee["verified_source"]>, string> = {
  institution_registry: "university registry",
  past_payment: "past payment",
  manual: "added by you",
};

const OUTCOMES: Record<Action["status"], string> = {
  awaiting_confirm: "Waiting",
  awaiting_otp: "Waiting",
  cooling_off: "Cooling off",
  executed: "Done",
  refused: "Refused",
  cancelled: "Cancelled",
  expired: "Expired",
};

/** One sentence of what approving will do. */
function sentence(action: Action): string {
  const cost = action.cost_breakdown;
  if (cost?.kind === "conversion") {
    return `Convert ${formatAmount(cost.amount_minor, cost.from_currency)} to ${cost.to_currency} via ${cost.provider_name}`;
  }
  return describeAction(action);
}

/** Where the payee's details come from, and whether the student has paid them before. */
function PayeeCheck({ payee }: { payee: Payee | undefined }) {
  const paid = payee?.first_paid_at ? `paid before on ${formatDate(payee.first_paid_at)}` : "never paid before";
  if (!payee?.verified_source) {
    return (
      <p className="flex items-center gap-2 text-13 font-medium text-amber-ink">
        <TriangleAlert aria-hidden className="size-4" />
        Not verified, {paid}
      </p>
    );
  }
  return (
    <p className="flex items-center gap-2 text-13 font-medium text-ink">
      <BadgeCheck aria-hidden className="size-4 text-teal" />
      Verified: {SOURCES[payee.verified_source]}, {paid}
    </p>
  );
}

function TierReason({ action, language, limit }: { action: Action; language: Language; limit: string }) {
  const [english, setEnglish] = useState(false);
  const overLimit = action.reasons.some((reason) => reason.code === "OVER_TXN_LIMIT");
  return (
    <div className="rounded-control border border-amber-line bg-amber-tint p-3">
      <div className="flex items-center justify-between gap-2">
        <TierBadge tier={tierOf(action.tier)} />
        {language !== "en" && (
          <Button variant="ghost" size="sm" icon={Languages} aria-pressed={english} onClick={() => setEnglish(!english)}>
            {english ? "Hide English" : "Show English"}
          </Button>
        )}
      </div>
      <p lang={language} className="mt-2 text-15 text-ink">
        {action.why[language]}
      </p>
      {english && (
        <p lang="en" className="mt-1 text-15 text-body">
          {action.why.en}
        </p>
      )}
      {overLimit && <p className="mt-1 text-13 text-amber-ink">Per-payment limit: {limit}</p>}
    </div>
  );
}

interface ApprovalSheetProps {
  /** The plan being reviewed, or null when the sheet is closed. */
  planId: string | null;
  actions: Action[];
  payees: Payee[];
  settings: DemoSettings;
  me: User;
  language: Language;
  onApprove: (action: Action, code: string) => Promise<ApproveResult>;
  /** Cancels the action and the later steps that depend on it. Resolves to an error message, or null. */
  onCancel: (action: Action) => Promise<string | null>;
  onClose: () => void;
}

/**
 * Where the student approves a plan, one action at a time: everything the action will do,
 * what it costs, and for Tier 3 the one-time code. It moves on to the next action by itself.
 */
export function ApprovalSheet({
  planId,
  actions,
  payees,
  settings,
  me,
  language,
  onApprove,
  onCancel,
  onClose,
}: ApprovalSheetProps) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<"approve" | "cancel" | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const plan = planId ? actions.filter((action) => action.plan_id === planId && action.tier !== "REFUSED") : [];
  const current = plan.find(isWaiting) ?? null;
  const currentId = current?.id ?? null;

  // A new action starts with an empty code field.
  useEffect(() => {
    setCode("");
  }, [currentId]);
  useEffect(() => {
    if (planId === null) setNote(null);
  }, [planId]);

  const needsCode = current?.requires.includes("otp") ?? false;
  const coolingOff = current?.status === "cooling_off";
  const cost = current?.cost_breakdown ?? null;

  async function approve() {
    if (!current || busy || (needsCode && code.length !== CODE_LENGTH)) return;
    setBusy("approve");
    setNote(null);
    const result = await onApprove(current, code);
    if (result.kind === "wrong_code") {
      setCode("");
      if (result.attemptsLeft > 0) {
        setNote(`Wrong code. ${result.attemptsLeft} ${result.attemptsLeft === 1 ? "attempt" : "attempts"} left.`);
      } else {
        // Three wrong codes cancel the action; the steps after it cannot run without it.
        await onCancel(current);
        setNote("Cancelled after three wrong codes.");
      }
    } else if (result.kind === "failed") {
      setNote(result.message);
    }
    setBusy(null);
  }

  async function cancel() {
    if (!current || busy) return;
    setBusy("cancel");
    const failure = await onCancel(current);
    setBusy(null);
    if (failure) setNote(failure);
    else onClose();
  }

  const footer = !current ? (
    <Button onClick={onClose}>Close</Button>
  ) : coolingOff ? (
    <Button variant="secondary" loading={busy === "cancel"} onClick={() => void cancel()}>
      Cancel payment
    </Button>
  ) : (
    <>
      <Button variant="secondary" loading={busy === "cancel"} disabled={busy === "approve"} onClick={() => void cancel()}>
        Cancel
      </Button>
      <Button
        loading={busy === "approve"}
        disabled={busy === "cancel" || (needsCode && code.length !== CODE_LENGTH)}
        onClick={() => void approve()}
      >
        Approve
      </Button>
    </>
  );

  return (
    <Sheet open={planId !== null} onClose={onClose} title="Review and approve" width="wide" footer={footer}>
      {current ? (
        <div className="flex flex-col gap-5">
          <div>
            {plan.length > 1 && (
              <Badge>
                Step {plan.indexOf(current) + 1} of {plan.length}
              </Badge>
            )}
            <p className="mt-2 font-heading text-18 font-semibold text-ink">{sentence(current)}</p>
            {cost?.kind === "payment" && (
              <div className="mt-2">
                <PayeeCheck payee={payees.find((payee) => payee.id === cost.payee_id)} />
              </div>
            )}
          </div>

          {coolingOff && current.cooling_off_until ? (
            <div className="flex flex-col items-center gap-3 py-4 text-center">
              <CountdownRing until={current.cooling_off_until} totalSeconds={settings.cooling_off_seconds} />
              <p className="max-w-xs text-15 text-body">A first payment to a new payee waits before it runs.</p>
            </div>
          ) : (
            <>
              {cost && <Rows rows={costRows(cost)} strong={["True cost", "Total"]} size="15" />}
              {cost?.kind === "conversion" && cost.warning && (
                <p className="flex items-start gap-2 text-13 font-medium text-amber-ink">
                  <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
                  {cost.warning}
                </p>
              )}
              <TierReason
                action={current}
                language={language}
                limit={formatAmount(me.per_txn_limit_minor, me.home_currency)}
              />
              {needsCode && (
                <div>
                  <label htmlFor="one-time-code" className="mb-1 block text-13 font-medium text-muted">
                    One-time code
                  </label>
                  <input
                    id="one-time-code"
                    value={code}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    aria-describedby="one-time-code-hint"
                    // Digits only, six at most: a pasted "246 810" still works.
                    onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, CODE_LENGTH))}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") void approve();
                    }}
                    className="h-12 w-44 rounded-control border border-line bg-surface px-3 font-heading text-24 tracking-[0.3em] text-ink tabular-nums"
                  />
                  <p id="one-time-code-hint" className="mt-1 text-13 text-muted">
                    Demo code: {settings.otp}
                  </p>
                </div>
              )}
            </>
          )}
          {note && (
            <p role="alert" className="text-15 font-medium text-danger">
              {note}
            </p>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          {note && (
            <p role="alert" className="text-15 font-medium text-danger">
              {note}
            </p>
          )}
          <p className="text-15 text-body">Nothing is waiting for you in this plan.</p>
          <ol className="flex flex-col gap-2">
            {plan.map((action) => (
              <li key={action.id} className="flex items-center justify-between gap-3">
                <span className="text-15 text-ink">{describeAction(action)}</span>
                <Badge tone={action.status === "executed" ? "success" : action.status === "refused" ? "danger" : "neutral"}>
                  {OUTCOMES[action.status]}
                </Badge>
              </li>
            ))}
          </ol>
        </div>
      )}
    </Sheet>
  );
}
