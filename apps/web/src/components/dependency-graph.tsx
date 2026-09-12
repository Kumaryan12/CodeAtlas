"use client";

import { useEffect, useMemo, useState } from "react";
import { GraphCanvas, languageColors, languageLabels } from "./graph-canvas";
import { request } from "@/lib/repositories";
import { visibleGraph, type DependencyGraph } from "@/lib/graph";

export function DependencyGraphView({ repositoryId, activeId, onSelect, onOpenCode }: {
  repositoryId: string; activeId: string | null; onSelect: (id: string) => void; onOpenCode: (id: string) => void;
}) {
  const [view, setView] = useState<"dependency" | "data_flow">("dependency");
  const isFlow = view === "data_flow";
  const [graph, setGraph] = useState<DependencyGraph | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [showUnconnected, setShowUnconnected] = useState(false);
  const [focus, setFocus] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [layoutVersion, setLayoutVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void request<DependencyGraph>(`/${repositoryId}/graph?view=${view}`, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setGraph(data); })
      .catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message); });
    return () => controller.abort();
  }, [repositoryId, attempt, view]);
  const visible = useMemo(() => graph ? visibleGraph(graph, query, language, focus ? activeId : null, 200, showUnconnected) : null, [graph, query, language, focus, activeId, showUnconnected]);
  const changeView = (next: "dependency" | "data_flow") => { if (next !== view) { setGraph(null); setError(""); setView(next); } };
  const viewSwitch = <div className="graph-scope" role="group" aria-label="Architecture view"><button aria-pressed={!isFlow} onClick={() => changeView("dependency")}>Dependencies</button><button aria-pressed={isFlow} onClick={() => changeView("data_flow")}>Data Flow</button></div>;
  if (error) return <section>{viewSwitch}<div className="notice error" role="alert">{error} <button className="secondary-button" onClick={() => { setError(""); setAttempt(attempt + 1); }}>Retry graph</button></div></section>;
  /* Graph data is cleared when switching views. */
  if (!graph || !visible) return <section>{viewSwitch}<p className="panel-empty" role="status">{isFlow ? "Tracing Python values between functions…" : "Resolving snapshot dependencies…"}</p></section>;
  const selected = graph.nodes.find((node) => node.id === activeId);
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const outgoing = graph.edges.filter((edge) => edge.source === activeId);
  const incoming = graph.edges.filter((edge) => edge.target === activeId);
  const unresolved = graph.unresolved.filter((issue) => issue.source === activeId);
  const cycle = graph.cycles.find((members) => activeId && members.includes(activeId));
  const directories = [...new Set(graph.nodes.map((node) => node.file.includes("/") ? node.file.split("/")[0] + "/" : ""))].filter(Boolean).sort();
  const resetFilters = () => { setQuery(""); setLanguage(""); setFocus(false); };
  return <section className="architecture-view" aria-label="Architecture">
    <header className="architecture-heading"><div><p className="eyebrow">REPOSITORY STRUCTURE</p><h2>{isFlow ? "Data-flow map" : "Dependency map"}</h2><p className="muted">{isFlow ? "Follow values from producer to consumer. Select a file to inspect the call-site evidence." : "An arrow points from the file that imports to the file it depends on."}</p></div><span className="graph-analysis-badge"><i />Static analysis</span></header>
    {viewSwitch}
    {isFlow && <p className="notice">Python static analysis · potential return-to-argument flow, not runtime execution. Class methods, external calls, and JavaScript/TypeScript flow are not analyzed.</p>}
    <div className="graph-summary">
      <div><span>Source files</span><strong>{graph.nodes.length.toLocaleString()}</strong><small>across the snapshot</small></div>
      <div><span>Connections</span><strong>{graph.edges.length.toLocaleString()}</strong><small>{isFlow ? "producer → consumer relationships" : "resolved local imports"}</small></div>
      <div><span>{isFlow ? "Scope" : "Unresolved"}</span><strong>{isFlow ? "Python" : graph.unresolved.length.toLocaleString()}</strong><small>{isFlow ? "explicit function return values" : "external or unlocated imports"}</small></div>
      <div className={graph.cycles.length ? "graph-cycle-stat" : ""}><span>{isFlow ? "Flow cycles" : "Import cycles"}</span><strong>{graph.cycles.length.toLocaleString()}</strong><small>groups of connected files</small></div>
    </div>
    <div className="graph-toolbar">
      <label className="graph-search">Find a file<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by path or filename…" /></label>
      <label>Language<select value={language} onChange={(event) => setLanguage(event.target.value)}><option value="">All languages</option><option value="python">Python</option><option value="javascript">JavaScript</option><option value="typescript">TypeScript</option></select></label>
      <div className="graph-scope" role="group" aria-label="Graph scope"><button aria-pressed={!focus} onClick={() => setFocus(false)}>Overview</button><button aria-pressed={focus} disabled={!activeId} onClick={() => setFocus(true)}>Neighborhood</button></div>
      <button className="graph-reset" onClick={() => setLayoutVersion((value) => value + 1)}>Reset layout</button>
    </div>
    {visible.unconnectedCount > 0 && <button className="secondary-button" aria-pressed={showUnconnected} onClick={() => setShowUnconnected(!showUnconnected)}>{showUnconnected ? "Hide" : "Show"} unconnected files ({visible.unconnectedCount})</button>}
    {!!directories.length && <div className="graph-directories" aria-label="Directory shortcuts"><span>JUMP TO</span>{directories.slice(0, 8).map((directory) => <button key={directory} aria-pressed={query === directory} onClick={() => setQuery(query === directory ? "" : directory)}>{directory}</button>)}</div>}
    <div className="graph-display-status"><span role="status"><strong>{visible.nodes.length}</strong> of {visible.total} matching files · {visible.edges.length} visible connections{focus && " · selected file + direct neighbors"}{!showUnconnected && visible.unconnectedCount > 0 && ` · ${visible.unconnectedCount} unconnected files hidden`}</span>{(query || language || focus) && <button onClick={resetFilters}>Clear filters</button>}</div>
    {visible.total > visible.nodes.length && <p className="notice warning">The canvas shows the first 200 matching files. Narrow the path or choose Neighborhood for a closer view.</p>}
    <div className="graph-layout">
      {visible.nodes.length ? <GraphCanvas key={`${view}:${layoutVersion}:${visible.nodes.map((node) => node.id).join(",")}`} graph={graph} visible={visible} dataFlow={isFlow} activeId={activeId} onSelect={onSelect} />
        : <div className="graph-empty"><span>⌕</span><h3>{!showUnconnected && visible.unconnectedCount > 0 ? "No connected files match" : "No matching files"}</h3><p className="muted">{!showUnconnected && visible.unconnectedCount > 0 ? "Use Show unconnected files to include files with no detected connections to other files in this view, or clear the filters." : "Try a different path or expand the graph scope."}</p><button className="secondary-button" onClick={resetFilters}>Clear filters</button></div>}
      <aside className="dependency-inspector" aria-label="Selected file connections">
        {selected ? <>
          <div className="inspector-heading"><p className="eyebrow">FILE DETAILS</p><span className="graph-file-icon" style={{ color: languageColors[selected.language] }}>{languageLabels[selected.language] ?? "{}"}</span></div>
          <h3>{selected.label}</h3><p className="inspector-path">{selected.file}</p>
          <div className="inspector-counts"><span><strong>{selected.symbol_count}</strong> symbols</span><span><strong>{outgoing.length + incoming.length}</strong> links</span></div>
          {!visible.nodes.some((node) => node.id === selected.id) && <p className="notice warning">This file is outside the current filters.</p>}
          <button className="primary-button" onClick={() => onOpenCode(selected.id)}>Open source & symbols ↗</button>
          {selected.warning && <p className="notice warning">{selected.warning}</p>}
          {cycle && <p className="notice warning">Part of a {cycle.length}-file {isFlow ? "flow" : "import"} cycle.</p>}
          <details className="inspector-section" open><summary>{isFlow ? "Values passed to" : "Imports"} <span>{outgoing.length}</span></summary>
          {outgoing.slice(0, 100).map((edge) => <div key={edge.id} className="dependency-item"><button onClick={() => onSelect(edge.target)}>{byId.get(edge.target)?.file}</button>
            <small>{edge.evidence.slice(0, 3).map((item) => `${item.context_file_path ? item.context_file_path + " · " : ""}${item.specifier}${item.line ? ` : L${item.line}` : ""} (${item.resolution.replaceAll("_", " ")})`).join("; ")}</small>{isFlow && edge.evidence.slice(0, 3).map((item, index) => item.context_file_id && <button key={index} onClick={() => onOpenCode(item.context_file_id!)}>Inspect call site · {item.context_file_path}:L{item.line}</button>)}</div>)}
          {!outgoing.length && <p className="muted">{isFlow ? "No supported outgoing value flow found." : "No resolved local imports."}</p>}
          </details><details className="inspector-section" open><summary>{isFlow ? "Values received from" : "Imported by"} <span>{incoming.length}</span></summary>
          {incoming.slice(0, 100).map((edge) => <div key={edge.id} className="dependency-item"><button onClick={() => onSelect(edge.source)}>{byId.get(edge.source)?.file}</button>{isFlow && edge.evidence.slice(0, 3).map((item, index) => <small key={index}>{item.context_file_path}:L{item.line} · {item.specifier}{item.context_file_id && <button onClick={() => onOpenCode(item.context_file_id!)}>Inspect call site</button>}</small>)}</div>)}
          {!incoming.length && <p className="muted">{isFlow ? "No supported incoming value flow found." : "No recorded incoming imports."}</p>}
          </details>{!isFlow && <details className="inspector-section"><summary>Unresolved <span>{unresolved.length}</span></summary>
          {unresolved.slice(0, 100).map((item, index) => <div className="dependency-item" key={index}><code>{item.specifier}</code><small>{item.reason.replaceAll("_", " ")}{item.line ? ` · L${item.line}` : ""}</small>
            {!!item.candidates.length && <small>Candidates: {item.candidates.join(", ")}</small>}</div>)}
          {!unresolved.length && <p className="muted">No unresolved observations for this file.</p>}</details>}
          {[outgoing.length, incoming.length, unresolved.length].some((count) => count > 100) && <p className="muted">Each list shows up to 100 entries. The graph API provides all results.</p>}
        </> : <p className="panel-empty">Select a file node to inspect its connections and source evidence.</p>}
      </aside>
    </div>
    <footer className="graph-legend"><div><span><i className="legend-line" />{isFlow ? "Returned value → consumer argument" : "Importer → imported file"}</span>{!isFlow && <span><i className="legend-line inferred" />Inferred Python root</span>}<span><i className="legend-line cycle" />Cycle edge</span></div><p>{isFlow ? "Potential static flow · absence of edges does not prove isolation" : "Static file imports · arrows do not represent data movement"}</p></footer>
    <details className="scan-summary"><summary>{isFlow ? "Coverage and analysis limits" : "Resolution notes"}{graph.legacy_files ? " · legacy snapshot" : ""}</summary>{graph.notes.map((note) => <p key={note}>{note}</p>)}</details>
  </section>;
}
