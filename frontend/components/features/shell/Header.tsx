import { CircleUserRound, Info, Play } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { HeaderStatus } from "./HeaderStatus";
import { LanguageSwitcher } from "./LanguageSwitcher";

export function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-line bg-surface">
      <p className="flex h-8 items-center gap-2 border-b border-line bg-paper px-8 text-13 text-body">
        <Info aria-hidden className="size-4 text-muted" />
        Sandbox demo: no real money moves
      </p>
      <div className="flex h-16 items-center gap-6 px-8">
        <HeaderStatus />
        <div className="ml-auto flex items-center gap-4">
          <LanguageSwitcher />
          <Button variant="secondary" icon={Play} disabled>
            Demo
          </Button>
          <span className="flex items-center gap-2 text-15 font-medium text-ink">
            <CircleUserRound aria-hidden className="size-5 text-muted" strokeWidth={1.75} />
            Ahmad Faris
          </span>
        </div>
      </div>
    </header>
  );
}
