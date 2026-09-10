"use client";

import { useEffect, useState } from "react";
import { request } from "@/lib/repositories";
import { currentTestResult, type TestProfile, type TestRun } from "@/lib/test-runs";
import type { AgentRun } from "@/lib/agent";

export function TestReview({ repositoryId, run, digest }: { repositoryId: string; run: AgentRun; digest: string | null }) {
  const [tests, setTests] = useState<TestRun[] | null>(null);
  const [profile, setProfile] = useState<TestProfile>(run.test_profile ?? "python-unittest");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const path = `/${repositoryId}/agent-runs/${run.id}/test-runs`;
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      try {
        const data = await request<TestRun[]>(path, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setTests(data); setError("");
        if (run.status === "running" || data.some((test) => test.status === "running")) timer = setTimeout(() => void refresh(), 2000);
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Could not load test results.");
      }
    }
    void refresh();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [path, run.status, revision]);

  async function start() {
    if (!digest || starting) return;
    setStarting(true); setError("");
    try {
      const created = await request<TestRun>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profile, workspace_digest: digest }) });
      setTests((previous) => [...(previous ?? []), created]);
      setRevision((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start tests.");
    } finally { setStarting(false); }
  }
  const current = currentTestResult(tests ?? [], digest);
  const busy = starting || run.status === "running" || !!tests?.some((test) => test.status === "running");
  return <section className="test-review" aria-label="Sandbox test results">
    <div className="agent-run-heading"><h3>Sandbox tests</h3><span className="trace-kind execute">EXECUTION</span></div>
    <p className="muted">Run imported source in an isolated container: no network, no installs, 30 seconds, 256 MiB memory. Results cover this source subset and the selected runner. Inspect test quality and coverage before relying on a successful exit.</p>
    <p className="ask-meta">{tests?.length ?? 0}/3 attempts used · Current draft: {!digest ? "refreshing version…" : current ? current.status === "passed" ? "command passed" : current.status.replaceAll("_", " ") : "not tested"}</p>
    {error && <p className="notice error" role="alert">{error} <button className="secondary-button" onClick={() => setRevision((value) => value + 1)}>Refresh tests</button></p>}
    <div className="test-controls">
      <label htmlFor={`test-profile-${run.id}`}>Test profile</label>
      <select id={`test-profile-${run.id}`} value={profile} disabled={busy} onChange={(event) => setProfile(event.target.value as TestProfile)}>
        <option value="python-unittest">Python unittest</option><option value="node-test">Node built-in tests (JS/TS)</option>
      </select>
      <button className="secondary-button" onClick={() => void start()} disabled={busy || !digest || !tests || tests.length >= 3}>{starting ? "Starting…" : "Run tests in sandbox"}</button>
    </div>
    {!tests ? <p role="status" className="muted">Loading test history…</p> : tests.map((test, i) => <details key={test.id} className="test-result" open={test.status !== "passed"}>
      <summary>Attempt {i + 1} · {test.profile} · {test.status.replaceAll("_", " ")} {digest && test.workspace_digest !== digest ? "· earlier draft" : ""}</summary>
      <p className="ask-meta">Exit {test.exit_code ?? "—"} · {(test.duration_ms / 1000).toFixed(2)} s · Workspace {test.workspace_digest.slice(0, 12)}</p>
      {test.error_code && <p className="notice warning">{test.error_code.replaceAll("_", " ")}</p>}
      <p className="ask-meta">stdout</p><pre tabIndex={0}>{test.stdout || "(empty)"}</pre>
      <p className="ask-meta">stderr</p><pre tabIndex={0}>{test.stderr || "(empty)"}</pre>
      <p className="ask-meta">Output is untrusted and capped at 32 KiB combined. Image {test.image_id?.slice(0, 19) ?? "unavailable"}.</p>
    </details>)}
  </section>;
}
