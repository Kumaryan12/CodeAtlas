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
export type AgentRun = RunSummary & {
  plan: string[];
  steps: {
    number: number;
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
