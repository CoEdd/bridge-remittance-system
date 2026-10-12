import type { Metadata } from "next";
import { Assistant } from "@/components/features/assistant/Assistant";

export const metadata: Metadata = { title: "Assistant" };

export default function AssistantPage() {
  return (
    <>
      {/* The sidebar already names the page; the whole height goes to the conversation. */}
      <h1 className="sr-only">Assistant</h1>
      <Assistant />
    </>
  );
}
