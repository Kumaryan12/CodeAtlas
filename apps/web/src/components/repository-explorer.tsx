"use client";

import { useEffect, useState } from "react";
import { fetchFiles, request, type FileDetail, type Repository, type RepositoryFile } from "@/lib/repositories";
import { FileTree } from "@/components/file-tree";
import { DependencyGraphView } from "@/components/dependency-graph";
import { RepositoryAgent } from "@/components/repository-agent";
import { RepositoryAsk } from "@/components/repository-ask";
import type { Citation } from "@/lib/qa";
import { CodeViewer } from "@/components/code-viewer";

function FileView({ repositoryId, fileId, citation }: { repositoryId: string; fileId: string; citation: Citation | null }) {
  const [file, setFile] = useState<FileDetail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void request<FileDetail>(`/${repositoryId}/files/${fileId}`, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setFile(data); })
      .catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message); });
    return () => controller.abort();
  }, [repositoryId, fileId]);
  if (error) return <p className="notice error" role="alert">{error}</p>;
  if (!file) return <p className="panel-empty" role="status">Loading source…</p>;
  return <CodeViewer key={`${file.id}:${citation?.start_line ?? 0}`} file={file} citation={citation} />;
}

export function RepositoryExplorer({ repository }: { repository: Repository }) {
  const [view, setView] = useState<"code" | "architecture" | "ask" | "agent">("code");
  const [citation, setCitation] = useState<Citation | null>(null);
  const [agentOpened, setAgentOpened] = useState(false);
  const [askOpened, setAskOpened] = useState(false);
  const [files, setFiles] = useState<RepositoryFile[] | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void fetchFiles(repository.id, controller.signal).then((data) => {
      if (!controller.signal.aborted) {
        setFiles(data);
        setActiveId(data[0]?.id ?? null);
      }
    }).catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message); });
    return () => controller.abort();
  }, [repository.id]);
  if (error) return <p className="notice error" role="alert">{error}</p>;
  if (!files) return <p className="panel-empty" role="status">Loading repository files…</p>;
  return <>
    <div className="repo-stats">
      <span><strong>{repository.file_count.toLocaleString()}</strong> source files</span>
      <span><strong>{repository.symbol_count.toLocaleString()}</strong> symbols</span>
      {Object.entries(repository.languages).map(([name, count]) => <span key={name}>{name} <strong>{Math.round(count / Math.max(repository.file_count, 1) * 100)}%</strong></span>)}
      <span>{Math.round(repository.source_bytes / 1024)} KB source</span>
    </div>
    {repository.warning_count > 0 && <p className="notice warning">{repository.warning_count} file(s) have parser warnings. Source remains available; symbols may be incomplete.</p>}
    <details className="scan-summary"><summary>Scan details · {Object.values(repository.skipped).reduce((a, b) => a + b, 0)} files skipped</summary>
      {Object.entries(repository.skipped).map(([reason, count]) => <span key={reason}>{reason.replaceAll("_", " ")}: {count}</span>)}
      <p>Python, JavaScript, and TypeScript source only. Language percentages are based on indexed file counts.</p>
    </details>
    <div className="workspace-tabs" aria-label="Repository view">
      <button aria-pressed={view === "code"} onClick={() => setView("code")}>Code</button>
      <button aria-pressed={view === "architecture"} onClick={() => setView("architecture")}>Architecture</button>
      <button aria-pressed={view === "ask"} onClick={() => { setAskOpened(true); setView("ask"); }}>Ask</button>
      <button aria-pressed={view === "agent"} onClick={() => { setAgentOpened(true); setView("agent"); }}>Agent</button>
    </div>
    {agentOpened && <div hidden={view !== "agent"}><RepositoryAgent repositoryId={repository.id} onOpenSource={(source) => { setCitation(source); setActiveId(source.file_id); setView("code"); }} /></div>}
    {askOpened && <div hidden={view !== "ask"}><RepositoryAsk repositoryId={repository.id} onOpenSource={(source) => { setCitation(source); setActiveId(source.file_id); setView("code"); }} /></div>}
    {view === "ask" || view === "agent" ? null : view === "architecture" ? <DependencyGraphView repositoryId={repository.id} activeId={activeId} onSelect={setActiveId}
      onOpenCode={(id) => { setCitation(null); setActiveId(id); setView("code"); }} /> : !files.length ? <div className="empty-state"><h2>No supported source files</h2><p className="muted">This snapshot contains no eligible Python, JavaScript, or TypeScript files. Review scan details above.</p></div>
      : <div className="explorer-grid"><FileTree files={files} activeId={activeId} onSelect={(id) => { setCitation(null); setActiveId(id); }} />
        {activeId && <FileView key={activeId} repositoryId={repository.id} fileId={activeId} citation={citation?.file_id === activeId ? citation : null} />}
      </div>}
  </>;
}
