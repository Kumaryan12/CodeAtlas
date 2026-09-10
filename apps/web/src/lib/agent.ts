import type { TestProfile } from "./test-runs";
import type { Citation } from "./qa";

export type RunStatus = "running" | "completed" | "failed" | "limited" | "interrupted";
export type RunSummary = {
  id: string;
  repository_id: string;
  task: string;
  mode: "investigate" | "edit";
  test_profile: TestProfile | null;
  status: RunStatus;
  model: string;
  created_at: string;
  finished_at: string | null;
  error_code: string | null;
  error_message: string | null;
};
export type UsageSummary = {
  recorded_calls: number;
  tokens_complete: boolean;
  known_input_tokens: number;
  known_output_tokens: number;
  provider_duration_ms: number;
  estimated_cost_usd: number | null;
};

export function usageLabel(usage?: UsageSummary): string {
  if (!usage?.recorded_calls) return "Usage unavailable · no provider measurements";
  const tokens = `${usage.known_input_tokens.toLocaleString()} input / ${usage.known_output_tokens.toLocaleString()} output tokens`;
  const cost = usage.estimated_cost_usd === null ? "cost not estimated" : `estimated $${usage.estimated_cost_usd.toFixed(6)}`;
  return `${tokens}${usage.tokens_complete ? "" : " (partial)"} · ${(usage.provider_duration_ms / 1000).toFixed(2)} s provider time · ${cost}`;
}

export type AgentRun = RunSummary & {
  usage_summary?: UsageSummary;
  plan: string[];
  steps: {
    number: number;
    transport?: "local" | "mcp" | null;
    kind: "model" | "read" | "write" | "execute";
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

export function traceCounts(steps: AgentRun["steps"]): { model: number; reads: number; writes: number; executions: number } {
  return {
    model: steps.filter((step) => step.kind === "model").length,
    executions: steps.filter((step) => step.kind === "execute").length,
    writes: steps.filter((step) => step.kind === "write").length,
    reads: steps.filter((step) => step.kind === "read").length,
  };
}


export type WorkspaceDiff = {
  run_id: string;
  commit_sha: string | null;
  workspace_digest: string;
  total: number;
  files: { path: string; status: "added" | "modified"; diff: string }[];
};

export function diffLineKind(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("diff --git") || line.startsWith("@@")) return "diff-heading";
  if (line.startsWith("+")) return "diff-addition";
  if (line.startsWith("-")) return "diff-deletion";
  return "diff-context";
}
