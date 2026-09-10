"use client";

import { useEffect, useState } from "react";
import { diffLineKind, type AgentRun, type WorkspaceDiff } from "@/lib/agent";
import { request } from "@/lib/repositories";

export function WorkspaceReview({ repositoryId, run }: { repositoryId: string; run: AgentRun }) {
  const [diff, setDiff] = useState<WorkspaceDiff | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const version = `${run.id}:${run.steps.length}:${run.status}:${revision}`;
  const [loadedVersion, setLoadedVersion] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void request<WorkspaceDiff>(`/${repositoryId}/agent-runs/${run.id}/diff`, { signal: controller.signal })
      .then((value) => { if (!controller.signal.aborted) { setDiff(value); setLoadedVersion(version); setError(""); } })
      .catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message); });
    return () => controller.abort();
  }, [repositoryId, run.id, version]);

  function download() {
    if (!diff || loadedVersion !== version || error || run.status === "running") return;
    const url = URL.createObjectURL(new Blob([diff.files.map((file) => file.diff).join("")], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url; link.download = `codeatlas-${run.id}.patch`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <section className="workspace-review" aria-label="Proposed changes">
    <div className="agent-run-heading"><h3>Proposed changes</h3><span className="ask-state">Untested draft</span></div>
    <p className="muted">This workspace contains imported source only. Review against the full repository before applying a downloaded patch. Files, configuration, and assets excluded during import are unavailable here.</p>
    {run.status !== "completed" && <p className="notice warning">{run.status === "running" ? "The agent is still working. This diff may change." : "This run did not complete. Any partial changes are preserved below for review."}</p>}
    {error && <p className="notice error" role="alert">{error} <button className="secondary-button" onClick={() => setRevision((value) => value + 1)}>Retry diff</button></p>}
    {!diff ? <p role="status" className="muted">Loading draft…</p> : <>
      <p className="ask-meta">{diff.total} changed files · Base snapshot {diff.commit_sha?.slice(0, 12) ?? "unknown"} · Snapshot citations still open original source.</p>
      {!diff.total ? <p className="muted">No proposed changes yet.</p> : <>
        <button className="secondary-button" onClick={download} disabled={run.status === "running" || !!error || loadedVersion !== version}>Download patch</button>
        {diff.files.map((file) => <details className="workspace-file" key={file.path} open>
          <summary><strong>{file.path}</strong> <span>{file.status}</span></summary>
          <pre tabIndex={0} aria-label={`Diff for ${file.path}`}><code>{file.diff.split("\n").map((line, i) => <span className={diffLineKind(line)} key={i}>{line}{"\n"}</span>)}</code></pre>
        </details>)}
      </>}
    </>}
  </section>;
}
