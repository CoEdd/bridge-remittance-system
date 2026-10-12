import type { Metadata } from "next";
import { Security } from "@/components/features/security/Security";
import { PageHeader } from "@/components/features/shell/PageHeader";

export const metadata: Metadata = { title: "Security" };

export default function SecurityPage() {
  return (
    <>
      <PageHeader title="Security" description="Eleven attacks, run live." />
      <Security />
    </>
  );
}
