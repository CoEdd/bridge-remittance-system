import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface EmptyStateProps {
  icon: LucideIcon;
  /** One sentence saying what is missing. */
  message: string;
  /** The one action the user can take from here. */
  action: ReactNode;
}

export function EmptyState({ icon: Icon, message, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-4 px-6 py-12 text-center">
      <span
        aria-hidden
        className="flex size-12 items-center justify-center rounded-full bg-teal-tint text-teal"
      >
        <Icon className="size-6" strokeWidth={1.75} />
      </span>
      <p className="max-w-md text-15 text-body">{message}</p>
      {action}
    </div>
  );
}
