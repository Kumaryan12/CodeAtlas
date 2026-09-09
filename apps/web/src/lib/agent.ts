import type { Citation } from "./qa";

export type RunStatus = "running" | "completed" | "failed" | "limited" | "interrupted";
export type RunSummary = {
  id: string;
  repository_id: string;
  task: string;
  status: RunStatus;
  model: string;
  created_at: string;
  finished_at: string | null;
  error_code: string | null;
  error_message: string | null;
};
export type AgentRun = RunSummary & {
  plan: string[];
  steps: {
    number: number;
    kind: "model" | "read";
    action: string;
    status: "running" | "completed" | "failed";
    started_at: string;
    duration_ms: number;
    summary: string;
    error_code: string | null;
  }[];
  result: {
    status: "answered" | "insufficient_context";
    claims: { text: string; citation_ids: string[] }[];
    citations: Citation[];
  } | null;
};
export type RunList = { items: RunSummary[]; total: number };

export function isRunActive(run: Pick<RunSummary, "status">): boolean {
  return run.status === "running";
}

export function traceCounts(steps: AgentRun["steps"]): { model: number; reads: number } {
  return {
    model: steps.filter((step) => step.kind === "model").length,
    reads: steps.filter((step) => step.kind === "read").length,
  };
}
