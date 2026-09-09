"use client";

import { useEffect, useMemo, useState } from "react";
import { Background, Controls, MarkerType, MiniMap, Position, ReactFlow, useNodesState } from "@xyflow/react";
import { request } from "@/lib/repositories";
import { layoutGraph, visibleGraph, type DependencyGraph } from "@/lib/graph";

function GraphCanvas({ graph, visible, activeId, onSelect }: {
  graph: DependencyGraph; visible: ReturnType<typeof visibleGraph>; activeId: string | null; onSelect: (id: string) => void;
}) {
  const positions = new Map(layoutGraph(visible.nodes, visible.edges, graph.cycles).map((item) => [item.id, item.position]));
  const [nodes, , onNodesChange] = useNodesState(visible.nodes.map((node) => ({
    id: node.id, position: positions.get(node.id)!, sourcePosition: Position.Right, targetPosition: Position.Left,
    data: { label: <div className="graph-node-label"><strong>{node.label}</strong><small>{node.file}</small><span>{node.language} · {node.symbol_count} symbols</span></div> },
    style: { width: 240 }, ariaLabel: `${node.file}, ${node.language}, ${node.symbol_count} symbols`,
  })));
  const edges = visible.edges.map((edge) => ({
    id: edge.id, source: edge.source, target: edge.target,
    markerEnd: { type: MarkerType.ArrowClosed, color: edge.in_cycle ? "#e5b578" : "#899fd4" },
    style: { stroke: edge.in_cycle ? "#e5b578" : "#899fd4", strokeDasharray: edge.evidence.some((item) => item.resolution === "python_inferred_root") ? "5 4" : undefined },
  }));
  return <div className="graph-canvas" aria-label="Repository import graph">
    <ReactFlow nodes={nodes.map((node) => ({ ...node, selected: node.id === activeId }))} edges={edges}
      onNodesChange={onNodesChange} onNodeClick={(_, node) => onSelect(node.id)}
      nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null}
      fitView minZoom={0.05} maxZoom={2} colorMode="dark" onlyRenderVisibleElements>
      <Background gap={22} size={1} /><Controls showInteractive={false} /><MiniMap pannable zoomable />
    </ReactFlow>
  </div>;
}

export function DependencyGraphView({ repositoryId, activeId, onSelect, onOpenCode }: {
  repositoryId: string; activeId: string | null; onSelect: (id: string) => void; onOpenCode: (id: string) => void;
}) {
  const [graph, setGraph] = useState<DependencyGraph | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState("");
  const [focus, setFocus] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    void request<DependencyGraph>(`/${repositoryId}/graph`, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setGraph(data); })
      .catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message); });
    return () => controller.abort();
  }, [repositoryId, attempt]);
  const visible = useMemo(() => graph ? visibleGraph(graph, query, language, focus ? activeId : null) : null, [graph, query, language, focus, activeId]);
  if (error) return <div className="notice error" role="alert">{error} <button className="secondary-button" onClick={() => { setError(""); setAttempt(attempt + 1); }}>Retry graph</button></div>;
  if (!graph || !visible) return <p className="panel-empty" role="status">Resolving snapshot dependencies…</p>;
  const selected = graph.nodes.find((node) => node.id === activeId);
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const outgoing = graph.edges.filter((edge) => edge.source === activeId);
  const incoming = graph.edges.filter((edge) => edge.target === activeId);
  const unresolved = graph.unresolved.filter((issue) => issue.source === activeId);
  const cycle = graph.cycles.find((members) => activeId && members.includes(activeId));
  return <section className="architecture-view" aria-label="Architecture">
    <div className="graph-summary"><strong>{graph.nodes.length} files</strong><span>{graph.edges.length} local import edges</span><span>{graph.unresolved.length} unresolved observations</span><span>{graph.cycles.length} cycle groups</span></div>
    <div className="graph-toolbar">
      <label>Filter path<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. apps/api/" /></label>
      <label>Language<select value={language} onChange={(event) => setLanguage(event.target.value)}><option value="">All languages</option><option value="python">Python</option><option value="javascript">JavaScript</option><option value="typescript">TypeScript</option></select></label>
      <label className="graph-focus"><input type="checkbox" checked={focus} disabled={!activeId} onChange={(event) => setFocus(event.target.checked)} />Selected file + direct neighbors</label>
    </div>
    <div className="graph-display-status" role="status">Showing {visible.nodes.length} of {visible.total} matching files ({graph.nodes.length} total). {visible.total > visible.nodes.length && "Canvas capped at 200 files; narrow the filter or focus on a file."}</div>
    <div className="graph-layout">
      {visible.nodes.length ? <GraphCanvas key={visible.nodes.map((node) => node.id).join(",")} graph={graph} visible={visible} activeId={activeId} onSelect={onSelect} />
        : <p className="panel-empty">No files match these filters.</p>}
      <aside className="dependency-inspector" aria-label="Selected file dependencies">
        {selected ? <>
          <p className="eyebrow">FILE / {selected.language}</p><h3>{selected.file}</h3><p>{selected.symbol_count} symbols · file node</p>
          <button className="primary-button" onClick={() => onOpenCode(selected.id)}>Open source & symbols ↗</button>
          {selected.warning && <p className="notice warning">{selected.warning}</p>}
          {cycle && <p className="notice warning">Part of a {cycle.length}-file import cycle.</p>}
          <h4>Imports · {outgoing.length}</h4>
          {outgoing.slice(0, 100).map((edge) => <div key={edge.id} className="dependency-item"><button onClick={() => onSelect(edge.target)}>{byId.get(edge.target)?.file}</button>
            <small>{edge.evidence.slice(0, 3).map((item) => `${item.specifier}${item.line ? ` : L${item.line}` : ""} (${item.resolution.replaceAll("_", " ")})`).join("; ")}</small></div>)}
          {!outgoing.length && <p className="muted">No resolved local imports.</p>}
          <h4>Imported by · {incoming.length}</h4>
          {incoming.slice(0, 100).map((edge) => <div key={edge.id} className="dependency-item"><button onClick={() => onSelect(edge.source)}>{byId.get(edge.source)?.file}</button></div>)}
          {!incoming.length && <p className="muted">No recorded incoming imports.</p>}
          <h4>Unresolved · {unresolved.length}</h4>
          {unresolved.slice(0, 100).map((item, index) => <div className="dependency-item" key={index}><code>{item.specifier}</code><small>{item.reason.replaceAll("_", " ")}{item.line ? ` · L${item.line}` : ""}</small>
            {!!item.candidates.length && <small>Candidates: {item.candidates.join(", ")}</small>}</div>)}
          {[outgoing.length, incoming.length, unresolved.length].some((count) => count > 100) && <p className="muted">Each list shows up to 100 entries. The graph API provides all results.</p>}
        </> : <p className="panel-empty">Select a file node to inspect its imports, dependents, and symbols.</p>}
      </aside>
    </div>
    <p className="graph-legend">Arrow: importer → dependency · dashed: inferred Python root · amber: cycle edge. This is a static import graph, not a call graph.</p>
    <details className="scan-summary"><summary>Resolution notes{graph.legacy_files ? " · legacy snapshot" : ""}</summary>{graph.notes.map((note) => <p key={note}>{note}</p>)}</details>
  </section>;
}
