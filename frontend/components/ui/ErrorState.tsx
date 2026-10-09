import { RefreshCw, TriangleAlert } from "lucide-react";
import { Button } from "./Button";

interface ErrorStateProps {
  /** One sentence saying what went wrong. */
  message: string;
  onRetry: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="flex flex-col items-center gap-4 px-6 py-8 text-center">
      <span
        aria-hidden
        className="flex size-12 items-center justify-center rounded-full bg-danger-tint text-danger"
      >
        <TriangleAlert className="size-6" strokeWidth={1.75} />
      </span>
      <p className="max-w-md text-15 text-body">{message}</p>
      <Button variant="secondary" icon={RefreshCw} onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}
