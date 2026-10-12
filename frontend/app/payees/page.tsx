import type { Metadata } from "next";
import { Payees } from "@/components/features/payees/Payees";
import { PageHeader } from "@/components/features/shell/PageHeader";

export const metadata: Metadata = { title: "Payees" };

export default function PayeesPage() {
  return (
    <>
      <PageHeader title="Payees" description="Who is verified, and who is not." />
      <Payees />
    </>
  );
}
