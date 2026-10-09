import { MessageSquare, Send } from "lucide-react";
import type { Metadata } from "next";
import { PageHeader } from "@/components/features/shell/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";

export const metadata: Metadata = { title: "Assistant" };

export default function AssistantPage() {
  return (
    <>
      <PageHeader title="Assistant" description="Ask Bridge about a bill or a payment request." />
      <Card>
        <EmptyState
          icon={MessageSquare}
          message="There is no conversation yet."
          action={
            <Button icon={Send} disabled>
              Ask a question
            </Button>
          }
        />
      </Card>
    </>
  );
}
