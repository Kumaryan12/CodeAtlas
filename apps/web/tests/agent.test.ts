import assert from "node:assert/strict";
import test from "node:test";
import { diffLineKind, isRunActive, traceCounts } from "../src/lib/agent.ts";
import { allowedRepositoryPath } from "../src/lib/proxy-policy.ts";

const id = "d8ad7614-0a30-4b7d-b499-1e1785be78bd";

test("investigation routes allow start and scoped reads without mutation endpoints", () => {
  assert.ok(allowedRepositoryPath([id, "agent-runs"], "POST"));
  assert.ok(allowedRepositoryPath([id, "agent-runs"], "GET"));
  assert.ok(allowedRepositoryPath([id, "agent-runs", id], "GET"));
  assert.equal(allowedRepositoryPath([id, "agent-runs", id], "POST"), false);
  assert.equal(allowedRepositoryPath([id, "agent-runs", id, "execute"], "POST"), false);
  assert.equal(allowedRepositoryPath([id, "agent-runs", ".."], "GET"), false);
});

test("terminal run states stop polling and counts include failed read attempts", () => {
  assert.ok(isRunActive({ status: "running" }));
  for (const status of ["completed", "failed", "limited", "interrupted"] as const) assert.equal(isRunActive({ status }), false);
  const step = { number: 1, kind: "model" as const, action: "choose_next_step", status: "completed" as const, started_at: "", duration_ms: 4, summary: "", error_code: null };
  assert.deepEqual(traceCounts([step, { ...step, number: 2, kind: "read", status: "failed" }]), { model: 1, reads: 1, writes: 0, executions: 0 });
});


test("diff endpoint is a scoped GET only", () => {
  assert.ok(allowedRepositoryPath([id, "agent-runs", id, "diff"], "GET"));
  for (const method of ["POST", "DELETE", "PATCH"]) assert.equal(allowedRepositoryPath([id, "agent-runs", id, "diff"], method), false);
  assert.equal(allowedRepositoryPath([id, "agent-runs", "..", "diff"], "GET"), false);
  assert.equal(allowedRepositoryPath([id, "agent-runs", id, "apply"], "GET"), false);
});

test("diff headers are distinguished from additions and deletions", () => {
  assert.equal(diffLineKind("+++ b/example.py"), "diff-heading");
  assert.equal(diffLineKind("+return value"), "diff-addition");
  assert.equal(diffLineKind("-return None"), "diff-deletion");
  assert.equal(diffLineKind(" unchanged"), "diff-context");
});
