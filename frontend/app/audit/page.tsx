import { ListChecks, ScrollText } from "lucide-react";
import type { Metadata } from "next";
import { PageHeader } from "@/components/features/shell/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";

export const metadata: Metadata = { title: "Audit log" };

export default function AuditPage() {
  return (
    <>
      <PageHeader
        title="Audit log"
        description="Every proposal, decision, approval and refusal, in order."
      />
      <Card>
        <EmptyState
          icon={ScrollText}
          message="No audit entries have been recorded yet."
          action={
            <Button icon={ListChecks} disabled>
              Verify chain
            </Button>
          }
        />
      </Card>
    </>
  );
}
