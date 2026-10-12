import {
  ArrowRight,
  FolderOpen,
  KeyRound,
  MessageSquare,
  ScrollText,
  Upload,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import type { Suggestion } from "@/components/features/assistant/model";

const ICONS: Record<Suggestion["kind"], LucideIcon> = {
  upload: Upload,
  demo: FolderOpen,
  ask: MessageSquare,
  approve: KeyRound,
  audit: ScrollText,
};

const CHIP =
  "flex items-start gap-2 rounded-card border border-line bg-surface px-3 py-2 text-left text-15 font-medium text-ink transition-colors duration-150 hover:border-teal hover:bg-teal-tint disabled:cursor-not-allowed disabled:bg-paper disabled:text-muted min-[1400px]:w-full min-[1400px]:py-3";

interface SuggestedNextProps {
  suggestions: Suggestion[];
  disabled: boolean;
  onPick: (suggestion: Suggestion) => void;
}

/**
 * The one or two things that make sense to do next. Clicking a chip does it.
 * A column from 1400px wide; on narrower screens one row, to leave the height to the conversation.
 */
export function SuggestedNext({ suggestions, disabled, onPick }: SuggestedNextProps) {
  return (
    <section
      aria-labelledby="suggested-next"
      className="flex flex-wrap items-center gap-x-4 gap-y-2 min-[1400px]:block"
    >
      <h2 id="suggested-next" className="font-heading text-18 font-semibold text-ink min-[1400px]:mb-3">
        Suggested next
      </h2>
      <ul className="flex flex-wrap gap-2 min-[1400px]:flex-col">
        {suggestions.map((suggestion) => {
          const Icon = ICONS[suggestion.kind];
          const icon = <Icon aria-hidden className="mt-0.5 size-5 shrink-0 text-teal" strokeWidth={1.75} />;
          return (
            <li key={suggestion.label}>
              {suggestion.kind === "audit" ? (
                <Link href="/audit" className={CHIP}>
                  {icon}
                  <span className="flex-1">{suggestion.label}</span>
                  <ArrowRight aria-hidden className="mt-0.5 size-4 text-muted" />
                </Link>
              ) : (
                <button type="button" disabled={disabled} onClick={() => onPick(suggestion)} className={CHIP}>
                  {icon}
                  <span lang={suggestion.kind === "ask" ? suggestion.language : undefined}>{suggestion.label}</span>
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
