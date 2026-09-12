"use client";

import { useMemo, useState } from "react";
import { Background, Controls, MarkerType, MiniMap, Panel, Position, ReactFlow, useNodesState, useReactFlow } from "@xyflow/react";
import { layoutGraph, type DependencyGraph, type visibleGraph } from "@/lib/graph";

export const languageColors: Record<string, string> = { python: "#78bca4", typescript: "#81aafa", javascript: "#e4c478" };
export const languageLabels: Record<string, string> = { python: "PY", typescript: "TS", javascript: "JS" };

function CanvasActions({ activeId }: { activeId: string | null }) {
  const { fitView } = useReactFlow();
  return <Panel position="top-left" className="graph-canvas-actions">
    <button onClick={() => void fitView({ padding: .2, duration: 300 })}>Fit map</button>
    <button disabled={!activeId} onClick={() => activeId && void fitView({ nodes: [{ id: activeId }], maxZoom: 1.2, duration: 300 })}>Find selected</button>
  </Panel>;
}

export function GraphCanvas({ graph, visible, activeId, onSelect, dataFlow = false }: {
  dataFlow?: boolean; graph: DependencyGraph; visible: ReturnType<typeof visibleGraph>; activeId: string | null; onSelect: (id: string) => void;
}) {
  const [showMap, setShowMap] = useState(false);
  const initialNodes = useMemo(() => {
    const positions = new Map(layoutGraph(visible.nodes, visible.edges, graph.cycles).map((item) => [item.id, item.position]));
    const connections = new Map<string, number>();
    for (const edge of visible.edges) for (const id of [edge.source, edge.target]) connections.set(id, (connections.get(id) ?? 0) + 1);
    return visible.nodes.map((node) => ({
      id: node.id, position: positions.get(node.id)!, sourcePosition: Position.Right, targetPosition: Position.Left,
      className: `architecture-file-node lang-${node.language}`,
      data: { label: <div className="graph-node-label">
        <div className="graph-node-title"><span className="graph-file-icon" style={{ color: languageColors[node.language] }}>{languageLabels[node.language] ?? "{}"}</span><strong title={node.file}>{node.label}</strong>{node.warning && <span className="graph-node-warning" title="Parser warning">!</span>}</div>
        <small title={node.file}>{node.file.includes("/") ? node.file.slice(0, node.file.lastIndexOf("/")) : "Repository root"}</small>
        <div className="graph-node-meta"><span>{node.symbol_count} symbols</span><span>{connections.get(node.id) ?? 0} visible links</span></div>
      </div> },
      style: { width: 250 }, ariaLabel: `${node.file}, ${node.language}, ${node.symbol_count} symbols`,
    }));
  }, [visible, graph.cycles]);
  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const connected = new Set(activeId ? [activeId] : []);
  for (const edge of visible.edges) {
    if (edge.source === activeId) connected.add(edge.target);
    if (edge.target === activeId) connected.add(edge.source);
  }
  const highlight = connected.size > 1;
  const edges = visible.edges.map((edge) => {
    const related = edge.source === activeId || edge.target === activeId;
    const color = edge.in_cycle ? "#e4b66d" : related ? "#aabafa" : "#46516a";
    return {
      id: edge.id, source: edge.source, target: edge.target, type: "smoothstep",
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
      style: { stroke: color, strokeWidth: related ? 2 : 1.25, opacity: highlight && !related ? .25 : .85, strokeDasharray: edge.evidence.some((item) => item.resolution === "python_inferred_root") ? "5 4" : undefined },
      label: dataFlow ? "passes value" : "imports",
      labelStyle: { fill: "#c8d1e5", fontSize: 10 },
      labelBgStyle: { fill: "#171d2b" },
      zIndex: related ? 2 : 0,
    };
  });
  const visibleSelection = visible.nodes.some((node) => node.id === activeId) ? activeId : null;
  return <div className="graph-canvas" aria-label={dataFlow ? "Repository data-flow graph" : "Repository import graph"}>
    <ReactFlow nodes={nodes.map((node) => ({ ...node, selected: node.id === activeId, style: { ...node.style, opacity: highlight && !connected.has(node.id) ? .4 : 1 } }))} edges={edges}
      onNodesChange={onNodesChange} onNodeClick={(_, node) => onSelect(node.id)}
      nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null}
      fitView fitViewOptions={{ padding: .18, maxZoom: 1 }} minZoom={0.05} maxZoom={2} colorMode="dark" onlyRenderVisibleElements>
      <Background gap={24} size={1} color="#2b3040" /><Controls showInteractive={false} />
      <CanvasActions activeId={visibleSelection} />
      <Panel position="top-right" className="graph-canvas-actions"><button aria-pressed={showMap} onClick={() => setShowMap(!showMap)}>Minimap</button></Panel>
      {showMap && <MiniMap pannable zoomable nodeColor={(node) => languageColors[visible.nodes.find((item) => item.id === node.id)?.language ?? ""] ?? "#858a9a"} maskColor="rgba(12, 14, 20, .7)" />}
      {!showMap && <Panel position="bottom-right" className="graph-canvas-hint">Drag to explore · scroll to zoom</Panel>}
    </ReactFlow>
  </div>;
}
