import type { DemoStepKey } from "@/lib/types";

export interface DemoStep {
  key: DemoStepKey;
  label: string;
  /** One line the presenter can read out. */
  caption: string;
  /** Where the step is shown. The invoice's source view needs its id, so it is a function. */
  path: (invoiceId: number | null) => string;
  /** The panel that gets a brief outline when the step is done. The last match is used. */
  flash: string;
}

const ASSISTANT = () => "/assistant";
const BLOCKED = "section[aria-label='Payment blocked']";

export const DEMO_STEPS: DemoStep[] = [
  {
    key: "upload",
    label: "Upload invoice",
    caption: "A real bill: Ahmad's tuition invoice, in English and Chinese",
    path: ASSISTANT,
    flash: "[data-demo='document']",
  },
  {
    key: "verify",
    label: "Read and verify",
    caption: "Every field is checked word for word against the source text",
    path: (invoiceId) => (invoiceId === null ? "/documents" : `/documents?id=${invoiceId}`),
    flash: "[data-demo='fields']",
  },
  {
    key: "plan",
    label: "Plan",
    caption: "One conversion covers the shortfall, with its true cost shown",
    path: ASSISTANT,
    flash: "[role='dialog']",
  },
  {
    key: "pay",
    label: "Approve and pay",
    caption: "The AI proposed. The policy engine decided Tier 3. Ahmad approves.",
    path: ASSISTANT,
    flash: "[data-demo='wallets']",
  },
  {
    key: "agent",
    label: "Fake agent",
    caption: "Neuro-symbolic claim check: the AI lists what the message claims; fixed rules check each claim",
    path: ASSISTANT,
    flash: BLOCKED,
  },
  {
    key: "mule",
    label: "Money mule",
    caption: "Money from a stranger, asked to pass it on: Bridge will not move it",
    path: ASSISTANT,
    flash: BLOCKED,
  },
  {
    key: "audit",
    label: "Audit proof",
    caption: "Change one record and the chain breaks",
    path: () => "/audit",
    flash: "[data-demo='tamper']",
  },
  {
    key: "redteam",
    label: "Red team",
    caption: "11 attacks, run live on an isolated copy",
    path: () => "/security",
    flash: "[data-demo='redteam-score']",
  },
  {
    key: "sources",
    label: "Rule sources",
    caption: "Facts come from official sources, cited, and approved by a person",
    path: () => "/sources",
    flash: "[data-demo='source-items']",
  },
];
