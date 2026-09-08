"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { ApiStatus } from "@/components/api-status";
import { RepositoryExplorer } from "@/components/repository-explorer";
import { request, type Page, type Repository } from "@/lib/repositories";

export function Workspace() {
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [total, setTotal] = useState(0);
  const [active, setActive] = useState<Repository | null>(null);
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    void request<Page<Repository>>("", { signal: controller.signal }).then((data) => {
      if (!controller.signal.aborted) {
        setRepositories(data.items);
        setTotal(data.total);
        setActive(data.items[0] ?? null);
      }
    }).catch((reason: Error) => {
      if (!controller.signal.aborted) setError(reason.message);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  async function refresh(append = false) {
    setLoading(true);
    setError("");
    try {
      const data = await request<Page<Repository>>(`?offset=${append ? repositories.length : 0}`);
      setRepositories((previous) => append ? [...previous, ...data.items] : data.items);
      setTotal(data.total);
      if (!append) setActive((previous) => data.items.find((repo) => repo.id === previous?.id) ?? data.items[0] ?? null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Cannot load repositories.");
    } finally {
      setLoading(false);
    }
  }

  async function importRepository(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setImporting(true);
    setError("");
    try {
      const repository = await request<Repository>("", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: url.trim() }),
      });
      setRepositories((previous) => [repository, ...previous]);
      setTotal((previous) => previous + 1);
      setActive(repository);
      setUrl("");
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "Import failed.";
      // Failed imports are also persisted. Refresh without hiding the original error.
      try {
        const data = await request<Page<Repository>>("");
        setRepositories(data.items);
        setTotal(data.total);
      } catch { /* Keep the last successfully loaded list. */ }
      setError(message);
    } finally {
      setImporting(false);
    }
  }

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to workspace</a>
    <header className="topbar">
      <Link href="/" className="brand"><span className="brand-mark">⌘</span>CodeAtlas</Link>
      <span className="divider">/</span><span className="text-sm text-zinc-400">Personal workspace</span>
      <span className="milestone">SOURCE INTELLIGENCE</span>
    </header>
    <div className="body-grid">
      <aside className="sidebar repo-sidebar">
        <div className="repository-nav-title"><p className="eyebrow">REPOSITORIES · {total}</p><button className="icon-button" disabled={loading || importing} onClick={() => void refresh()} aria-label="Refresh repositories">↻</button></div>
        {loading && <p className="panel-empty" role="status">Loading snapshots…</p>}
        <nav className="repository-list" aria-label="Repository snapshots">{repositories.map((repository) => <button
          key={repository.id} className={active?.id === repository.id ? "repo-entry selected" : "repo-entry"}
          onClick={() => setActive(repository)} aria-current={active?.id === repository.id ? "true" : undefined}>
          <strong title={repository.full_name}>{repository.full_name}</strong>
          <span>{repository.commit_sha?.slice(0, 7) ?? "snapshot"} · {repository.status}</span>
        </button>)}</nav>
        {repositories.length < total && <button className="secondary-button" disabled={loading || importing} onClick={() => void refresh(true)}>Load more snapshots</button>}
        {!loading && !repositories.length && <p className="panel-empty">Your imported repositories will appear here.</p>}
        <div className="sidebar-bottom"><p>Source analysis only.<br/>Repository code is never executed.</p><ApiStatus /></div>
      </aside>
      <main id="main-content" className="workspace-main">
        <div className="page-heading"><div><p className="eyebrow">EXPLORE THE SOURCE</p><h1>{active?.full_name ?? "Your next codebase, understood."}</h1>
          <p className="muted">{active?.description ?? "Import a public GitHub repository to explore its files and symbols."}</p></div><span className="badge">Read only</span></div>
        <form className="import-form" onSubmit={(event) => void importRepository(event)}>
          <label htmlFor="repository-url">Public GitHub repository</label>
          <div className="import-controls"><input id="repository-url" name="url" type="url" required maxLength={255}
            placeholder="https://github.com/owner/repository" value={url} disabled={importing}
            onChange={(event) => setUrl(event.target.value)} aria-describedby="import-help" />
            <button className="primary-button" disabled={importing || loading} type="submit">{importing ? "Analyzing…" : "Import repository"}<span aria-hidden="true"> ↗</span></button></div>
          <p id="import-help">Default branch · immutable commit snapshot · Python, JavaScript & TypeScript</p>
        </form>
        {error && <div className="notice error" role="alert">{error}</div>}
        {importing && <div className="notice progress" role="status"><span className="spinner"/>Downloading and analyzing source… This can take up to two minutes. Keep this page open.</div>}
        {active ? <>
          <div className="snapshot-bar"><span className={`status-badge status-${active.status}`}>{active.status === "ready" ? "Indexed" : active.status}</span>
            <span>⑂ {active.branch ?? "branch pending"}</span>
            {active.commit_sha && <a href={`${active.url}/tree/${active.commit_sha}`} target="_blank" rel="noreferrer">{active.commit_sha.slice(0, 12)} ↗</a>}
            <span title={active.created_at}>{new Date(active.created_at).toLocaleString()}</span>
          </div>
          {active.status === "failed" && <div className="notice error">{active.error_message} Enter the URL above to create a new import.</div>}
          {active.status === "importing" && <div className="notice progress">Import is in progress. Refresh the repository list to check its result. An interrupted API process can leave an unfinished snapshot; importing the URL again creates a new one.</div>}
          {(active.status === "ready" || active.status === "partial") && <RepositoryExplorer key={active.id} repository={active} />}
        </> : !loading && <section className="empty-state" aria-labelledby="empty-title">
          <div className="map-art" aria-hidden="true"><span className="map-node">{"{ }"}</span><span className="map-line"/><span className="map-node center">⌘</span><span className="map-line"/><span className="map-node">{"</>"}</span></div>
          <p className="eyebrow accent">EVERY CONNECTION STARTS SOMEWHERE</p><h2 id="empty-title">Get to know your codebase.</h2>
          <p className="empty-copy">Browse source. Find functions. Understand the structure.<br/>Import a repository above to build your first snapshot.</p>
        </section>}
        <footer><span>CODEATLAS / DETERMINISTIC SOURCE ANALYSIS</span><span>Dependency graphs arrive in Milestone 2</span></footer>
      </main>
    </div>
  </div>;
}
