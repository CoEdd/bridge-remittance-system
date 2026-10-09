import type { Metadata } from "next";
import { Documents } from "@/components/features/documents/Documents";
import { PageHeader } from "@/components/features/shell/PageHeader";

export const metadata: Metadata = { title: "Documents" };

export default function DocumentsPage() {
  return (
    <>
      <PageHeader title="Documents" description="Invoices and payment messages Bridge has read." />
      <Documents />
    </>
  );
}
