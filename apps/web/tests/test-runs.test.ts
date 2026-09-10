import assert from "node:assert/strict";
import test from "node:test";
import { currentTestResult, type TestRun } from "../src/lib/test-runs.ts";
import { allowedRepositoryPath } from "../src/lib/proxy-policy.ts";

const id = "d8ad7614-0a30-4b7d-b499-1e1785be78bd";
const row: TestRun = { id, run_id: id, profile: "python-unittest", workspace_digest: "a", status: "passed", image_id: null, exit_code: 0, stdout: "", stderr: "", duration_ms: 10, error_code: null, created_at: "", finished_at: "" };

test("test status uses the latest attempt for the exact draft version", () => {
  assert.equal(currentTestResult([row], "b"), null);
  assert.equal(currentTestResult([row], null), null);
  assert.equal(currentTestResult([row], "a")?.status, "passed");
  const pending = { ...row, status: "running" as const, exit_code: null };
  assert.equal(currentTestResult([row, pending], "a")?.status, "running");
  assert.equal(currentTestResult([row, { ...row, workspace_digest: "b", status: "failed" }], "b")?.status, "failed");
});

test("only exact scoped test history and start routes pass the proxy", () => {
  assert.ok(allowedRepositoryPath([id, "agent-runs", id, "test-runs"], "GET"));
  assert.ok(allowedRepositoryPath([id, "agent-runs", id, "test-runs"], "POST"));
  assert.equal(allowedRepositoryPath([id, "agent-runs", "..", "test-runs"], "POST"), false);
  assert.equal(allowedRepositoryPath([id, "agent-runs", id, "test-runs", "shell"], "POST"), false);
  assert.equal(allowedRepositoryPath([id, "agent-runs", id, "execute"], "POST"), false);
  assert.equal(allowedRepositoryPath([id, "agent-runs", id, "test-runs"], "DELETE"), false);
});
