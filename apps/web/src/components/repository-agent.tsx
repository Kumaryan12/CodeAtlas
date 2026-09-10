"use client";

import { useEffect, useState, type FormEvent } from "react";
import { WorkspaceReview } from "./workspace-review";
import { request } from "@/lib/repositories";
import { citationLabel, type Citation, type IndexStatus } from "@/lib/qa";
import { isRunActive, traceCounts, type AgentRun, type RunList } from "@/lib/agent";

export function RepositoryAgent({ repositoryId, onOpenSource }: {
  repositoryId: string;
  onOpenSource: (citation: Citation) => void;
}) {
  const [mode, setMode] = useState<"investigate" | "edit">("investigate");
  const [testProfile, setTestProfile] = useState<"" | "python-unittest" | "node-test">("");
  const [task, setTask] = useState("");
  const [history, setHistory] = useState<RunList | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [index, setIndex] = useState<IndexStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      try {
        const data = await request<RunList>(`/${repositoryId}/agent-runs`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setHistory(data);
        setSelectedId((previous) => previous ?? data.items[0]?.id ?? null);
        if (data.items.some(isRunActive)) timer = setTimeout(() => void refresh(), 2000);
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Could not load investigations.");
      }
    }
    void refresh();
    void request<IndexStatus>(`/${repositoryId}/index`, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setIndex(data); })
      .catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message); });
    return () => { controller.abort(); clearTimeout(timer); };
  }, [repositoryId, revision]);

  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const data = await request<AgentRun>(`/${repositoryId}/agent-runs/${selectedId}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setRun(data);
        if (isRunActive(data)) timer = setTimeout(() => void poll(), 2000);
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Could not load the trace.");
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [repositoryId, selectedId, revision]);

  async function start(event: FormEvent) {
    event.preventDefault();
    if (!task.trim() || starting || history?.items.some(isRunActive)) return;
    setStarting(true); setError("");
    try {
      const created = await request<AgentRun>(`/${repositoryId}/agent-runs`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ task: task.trim(), mode, test_profile: mode === "edit" && testProfile ? testProfile : null }),
      });
      setSelectedId(created.id); setRun(created); setTask("");
      setRevision((value) => value + 1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start investigation.");
    } finally { setStarting(false); }
  }

  const current = run?.id === selectedId ? run : null;
  const counts = traceCounts(current?.steps ?? []);
  const busy = starting || !!history?.items.some(isRunActive) || !!(current && isRunActive(current));
  return <section className="agent-panel" aria-label="Repository agent">
    <div className="ask-heading"><div><p className="eyebrow">REPOSITORY AGENT</p><h2>Investigate. Propose. Review.</h2>
      <p className="muted">Investigate source or ask the agent to prepare a draft for review.</p></div><span className="ask-state">{mode === "edit" ? "Isolated draft" : "Read-only"}</span></div>
    <p className="agent-boundary">{mode === "edit" ? (testProfile ? "Draft mode with tests: up to 20 tools, 21 model decisions and 3 test attempts. The agent may make two repair/retest iterations." : "Draft mode adds source reads, edits, file creation, and diff review in a separate workspace. Up to 10 tools and 11 model decisions. Your snapshot is preserved.") : "Allowed: list files, find symbols, search code, read excerpts, inspect dependencies. Up to 5 read actions and 6 model decisions per run."}</p>
    {error && <p className="notice error" role="alert">{error}</p>}
    <button className="secondary-button" disabled={starting} onClick={() => { setError(""); setRevision((value) => value + 1); }}>Refresh runs and configuration</button>
    {index && !index.reasoning_configured && <p className="notice warning">Set {index.reasoning_key_name} on the API server and restart it to enable investigations.</p>}
    {index?.reasoning_configured && index.status !== "ready" && <p className="notice warning">Search requires a semantic index. Build one in Ask for better coverage; file reads and dependency inspection work without it.</p>}
    <form className="ask-form agent-form" onSubmit={(event) => void start(event)}>
      <label htmlFor="agent-mode">Run mode</label>
      <select id="agent-mode" value={mode} disabled={busy} onChange={(event) => setMode(event.target.value as "investigate" | "edit")}>
        <option value="investigate">Investigate (read-only)</option><option value="edit">Propose edits (isolated draft)</option>
      </select>
      {mode === "edit" && <>
        <label htmlFor="agent-tests">Agent test permission</label>
        <select id="agent-tests" value={testProfile} disabled={busy} onChange={(event) => setTestProfile(event.target.value as typeof testProfile)}>
          <option value="">No execution — review draft first</option>
          <option value="python-unittest">Allow Python unittest and bounded retries</option>
          <option value="node-test">Allow Node tests and bounded retries (JS/TS)</option>
        </select>
        {testProfile && <p className="muted">Starting this run permits execution of imported and generated source in the selected sandbox profile. No network or dependency installs. Test output may be sent to the model to guide repairs.</p>}
      </>}
      <label htmlFor="investigation-task">{mode === "edit" ? "Change request" : "Investigation task"}</label>
      <textarea id="investigation-task" rows={3} maxLength={1500} value={task} disabled={busy || !index?.reasoning_configured}
        onChange={(event) => setTask(event.target.value)} placeholder={mode === "edit" ? "Add validation to the login input and prepare a small diff…" : "Trace authentication and identify validation gaps…"} />
      <div><p className="muted">The task and inspected source are sent to {index?.reasoning_provider ?? "the reasoning provider"} ({index?.answer_model ?? "configured model"}). Runs are saved locally; model usage may incur charges. Runs continue if you leave this view.</p>
        <button className="primary-button" disabled={busy || !task.trim() || !index?.reasoning_configured}>{starting ? "Starting…" : busy ? "Investigation running…" : (mode === "edit" ? "Prepare draft" : "Start investigation")}</button></div>
    </form>
    <div className="agent-layout"><aside className="agent-history" aria-label="Investigation history"><p className="eyebrow">RECENT RUNS</p>
      {!history ? <p className="muted" role="status">Loading runs…</p> : !history.items.length ? <p className="muted">No investigations yet.</p> : history.items.map((item) =>
        <button key={item.id} className={item.id === selectedId ? "selected" : ""} onClick={() => { setSelectedId(item.id); setError(""); }} title={item.task}>
          <strong>{item.task}</strong><span>{item.mode === "edit" ? "Draft" : "Investigation"} · {item.status} · {new Date(item.created_at).toLocaleString()}</span></button>)}
      {history && history.total > history.items.length && <p className="ask-meta">Showing the latest {history.items.length} of {history.total} runs.</p>}
    </aside><div className="agent-detail">
      {!selectedId ? <p className="muted">Start an investigation to inspect its plan and execution trace.</p> : !current ? <p role="status" className="muted">Loading trace…</p> : <>
        <div className="agent-run-heading"><h3>{current.task}</h3><span className="ask-state">{current.status}</span></div>
        <p className="ask-meta">{current.model} · {counts.model}/{current.test_profile ? 21 : current.mode === "edit" ? 11 : 6} model decisions · {counts.reads + counts.writes + counts.executions}/{current.test_profile ? 20 : current.mode === "edit" ? 10 : 5} tool attempts ({counts.writes} writes, {counts.executions} executions)</p>
        {current.error_message && <p className="notice warning" role="status">{current.error_message}</p>}
        {!!current.plan.length && <div className="agent-plan"><p className="eyebrow">PLAN</p><ol>{current.plan.map((step, i) => <li key={i}>{step}</li>)}</ol></div>}
        <div className="agent-trace" aria-live="polite"><p className="eyebrow">EXECUTION TRACE</p>
          {!current.steps.length && <p role="status" className="muted">Waiting for the first model step…</p>}
          <ol>{current.steps.map((step) => <li key={step.number}>
            <div><span className={`trace-kind ${step.kind}`}>{step.transport === "mcp" ? "READ · MCP" : step.kind === "model" ? "MODEL · REMOTE" : step.action === "search_code" ? "READ · REMOTE EMBEDDING" : step.kind === "write" ? "DRAFT WRITE" : step.kind === "execute" ? "EXECUTION · SANDBOX" : "READ"}</span><strong>{step.action.replaceAll("_", " ")}</strong>
              <span className="trace-status">{step.status} {step.status !== "running" && `· ${(step.duration_ms / 1000).toFixed(2)} s`}</span></div>
            {step.summary && <p>{step.summary}</p>}</li>)}</ol></div>
        {current.mode === "edit" && <WorkspaceReview key={current.id} repositoryId={repositoryId} run={current} />}
        {current.result && <section className="agent-result"><p className="eyebrow">FINDINGS</p>
          {current.result.status === "insufficient_context" ? <p className="notice warning">{current.mode === "edit" ? "No supported snapshot findings were returned. Review the draft separately above." : "The agent did not gather enough evidence for a supported answer. Try a narrower task or build the semantic index."}</p>
            : current.result.claims.map((claim, i) => <div key={i} className="ask-claim"><p>{claim.text}</p><div className="citation-links">{[...new Set(claim.citation_ids)].map((id) => {
              const citation = current.result?.citations.find((item) => item.id === id);
              return citation ? <button key={id} onClick={() => onOpenSource(citation)}>{citationLabel(citation)}</button> : null;
            })}</div></div>)}
          <p className="ask-meta">Verify findings against source. Valid citations do not guarantee that a claim is correct.</p>
        </section>}
      </>}
    </div></div>
  </section>;
}
