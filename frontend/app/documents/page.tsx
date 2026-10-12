import type { Metadata } from "next";
import { Documents } from "@/components/features/documents/Documents";
import { PageHeader } from "@/components/features/shell/PageHeader";

export const metadata: Metadata = { title: "Documents" };

/** `/documents?id=3` opens document 3. */
export default async function DocumentsPage({ searchParams }: { searchParams: Promise<{ id?: string }> }) {
  const id = Number((await searchParams).id);
  return (
    <>
      <PageHeader title="Documents" description="Invoices and payment messages Bridge has read." />
      <Documents initialId={Number.isInteger(id) && id > 0 ? id : null} />
    </>
  );
}
