import type { Metadata } from "next";
import { AuditLog } from "@/components/features/audit/AuditLog";
import { PageHeader } from "@/components/features/shell/PageHeader";

export const metadata: Metadata = { title: "Audit log" };

export default function AuditPage() {
  return (
    <>
      <PageHeader title="Audit log" description="Every step, in a hash-chained log." />
      <AuditLog />
    </>
  );
}
