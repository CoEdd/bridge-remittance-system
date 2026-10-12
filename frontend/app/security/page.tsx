import { ArrowDown } from "lucide-react";
import type { Metadata } from "next";
import { Security } from "@/components/features/security/Security";
import { PageHeader } from "@/components/features/shell/PageHeader";
import { buttonClasses } from "@/components/ui/Button";

export const metadata: Metadata = { title: "Security" };

export default function SecurityPage() {
  return (
    <>
      <PageHeader
        title="Security"
        description="What Bridge may do, and proof that the limits hold."
        action={
          <a href="#red-team" className={buttonClasses("secondary")}>
            Red-team suite
            <ArrowDown aria-hidden className="size-4" />
          </a>
        }
      />
      <Security />
    </>
  );
}
