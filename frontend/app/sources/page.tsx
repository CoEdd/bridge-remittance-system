import type { Metadata } from "next";
import { PageHeader } from "@/components/features/shell/PageHeader";
import { RuleSources } from "@/components/features/sources/RuleSources";

export const metadata: Metadata = { title: "Rule sources" };

export default function RuleSourcesPage() {
  return (
    <>
      <PageHeader title="Rule sources" description="Bridge uses a fact only after a person approves it." />
      <RuleSources />
    </>
  );
}
