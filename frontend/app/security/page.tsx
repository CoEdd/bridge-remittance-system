import { Play, ShieldCheck } from "lucide-react";
import type { Metadata } from "next";
import { PageHeader } from "@/components/features/shell/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";

export const metadata: Metadata = { title: "Security" };

export default function SecurityPage() {
  return (
    <>
      <PageHeader title="Security" description="Permission tiers and the red-team suite." />
      <Card>
        <EmptyState
          icon={ShieldCheck}
          message="The red-team suite has not been run yet."
          action={
            <Button icon={Play} disabled>
              Run red-team suite
            </Button>
          }
        />
      </Card>
    </>
  );
}
