export type TestProfile = "python-unittest" | "node-test";
export type TestRun = {
  id: string;
  run_id: string;
  profile: TestProfile;
  workspace_digest: string;
  status: "running" | "passed" | "failed" | "timeout" | "output_limit" | "error" | "interrupted";
  image_id: string | null;
  exit_code: number | null;
  stdout: string;
  stderr: string;
  duration_ms: number;
  error_code: string | null;
  created_at: string;
  finished_at: string | null;
};

export function currentTestResult(tests: TestRun[], digest: string | null): TestRun | null {
  if (!digest) return null;
  return tests.findLast((test) => test.workspace_digest === digest) ?? null;
}
