export type AgentMode = "live" | "scripted";

export type Currency = "MYR" | "CNY" | "USD";

/** Response of GET /health. */
export interface Health {
  status: "ok";
  agent_mode: AgentMode;
  /** Demo business date, YYYY-MM-DD. */
  demo_today: string;
  version: string;
}
