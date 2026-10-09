import { ArrowRight, Wallet } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/features/shell/PageHeader";
import { buttonClasses } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";

export default function HomePage() {
  return (
    <>
      <PageHeader title="Home" description="Wallets, upcoming bills and recent activity." />
      <Card>
        <EmptyState
          icon={Wallet}
          message="There are no wallets or bills to show yet."
          action={
            <Link href="/assistant" className={buttonClasses("secondary")}>
              Open Assistant
              <ArrowRight aria-hidden className="size-4" />
            </Link>
          }
        />
      </Card>
    </>
  );
}
