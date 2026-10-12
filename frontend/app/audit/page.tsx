import type { Metadata } from "next";
import { AuditLog } from "@/components/features/audit/AuditLog";
import { PageHeader } from "@/components/features/shell/PageHeader";

export const metadata: Metadata = { title: "Audit log" };

/** `/audit?entry=28` opens entry 28. */
export default async function AuditPage({ searchParams }: { searchParams: Promise<{ entry?: string }> }) {
  const entry = Number((await searchParams).entry);
  return (
    <>
      <PageHeader title="Audit log" description="Every step, in a hash-chained log." />
      <AuditLog initialEntry={Number.isInteger(entry) && entry > 0 ? entry : null} />
    </>
  );
}
