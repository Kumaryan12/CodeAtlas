import assert from "node:assert/strict";
import test from "node:test";
import { isRunActive, traceCounts } from "../src/lib/agent.ts";
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
  assert.deepEqual(traceCounts([step, { ...step, number: 2, kind: "read", status: "failed" }]), { model: 1, reads: 1 });
});
