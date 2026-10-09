import { UserPlus, Users } from "lucide-react";
import type { Metadata } from "next";
import { PageHeader } from "@/components/features/shell/PageHeader";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";

export const metadata: Metadata = { title: "Payees" };

export default function PayeesPage() {
  return (
    <>
      <PageHeader title="Payees" description="People and organisations that can be paid." />
      <Card>
        <EmptyState
          icon={Users}
          message="No payees have been added yet."
          action={
            <Button icon={UserPlus} disabled>
              Add payee
            </Button>
          }
        />
      </Card>
    </>
  );
}
