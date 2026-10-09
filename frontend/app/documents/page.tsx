import { FileText, Upload } from "lucide-react";
import type { Metadata } from "next";
import { PageHeader } from "@/components/features/shell/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";

export const metadata: Metadata = { title: "Documents" };

export default function DocumentsPage() {
  return (
    <>
      <PageHeader
        title="Documents"
        description="Invoices and payment messages that Bridge has read."
      />
      <Card>
        <EmptyState
          icon={FileText}
          message="No documents have been uploaded yet."
          action={
            <Button icon={Upload} disabled>
              Upload document
            </Button>
          }
        />
      </Card>
    </>
  );
}
