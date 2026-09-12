export type GraphNode = {
  id: string; label: string; type: "file"; file: string; language: string;
  symbol_count: number; warning: string | null;
};
export type GraphEdge = {
  id: string; source: string; target: string; relationship: "imports" | "data_flow"; in_cycle: boolean;
  evidence: { specifier: string; line: number | null; kind: string; resolution: string; context_file_id?: string | null; context_file_path?: string | null }[];
};
export type DependencyGraph = {
  repository_id: string; nodes: GraphNode[]; edges: GraphEdge[];
  unresolved: { source: string; specifier: string; line: number | null; reason: string; candidates: string[] }[];
  cycles: string[][]; notes: string[]; legacy_files: number;
};

export function visibleGraph(graph: DependencyGraph, query: string, language: string, focus: string | null, limit = 200, showUnconnected = false) {
  const neighbors = new Set<string>(focus ? [focus] : []);
  if (focus) for (const edge of graph.edges) {
    if (edge.source === focus) neighbors.add(edge.target);
    if (edge.target === focus) neighbors.add(edge.source);
  }
  const connected = new Set(graph.edges.filter((edge) => edge.source !== edge.target).flatMap((edge) => [edge.source, edge.target]));
  const unconnectedCount = graph.nodes.filter((node) => !connected.has(node.id)).length;
  const matching = graph.nodes.filter((node) =>
    (showUnconnected || connected.has(node.id)) &&
    node.file.toLowerCase().includes(query.toLowerCase()) && (!language || node.language === language) &&
    (!focus || neighbors.has(node.id)));
  matching.sort((a, b) => Number(b.id === focus) - Number(a.id === focus) || a.file.localeCompare(b.file));
  const nodes = matching.slice(0, limit);
  const ids = new Set(nodes.map((node) => node.id));
  return { nodes, edges: graph.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)), total: matching.length, unconnectedCount };
}

export function layoutGraph(nodes: GraphNode[], edges: GraphEdge[], cycles: string[][]) {
  const group = new Map(nodes.map((node) => [node.id, node.id]));
  cycles.forEach((members, index) => members.forEach((id) => { if (group.has(id)) group.set(id, `cycle-${index}`); }));
  const groups = [...new Set(group.values())].sort();
  const next = new Map(groups.map((id) => [id, new Set<string>()]));
  const degree = new Map(groups.map((id) => [id, 0]));
  const rank = new Map(groups.map((id) => [id, 0]));
  for (const edge of edges) {
    const source = group.get(edge.source), target = group.get(edge.target);
    if (source && target && source !== target && !next.get(source)!.has(target)) {
      next.get(source)!.add(target);
      degree.set(target, degree.get(target)! + 1);
    }
  }
  const queue = groups.filter((id) => degree.get(id) === 0);
  for (let index = 0; index < queue.length; index++) {
    const source = queue[index];
    for (const target of next.get(source)!) {
      rank.set(target, Math.max(rank.get(target)!, rank.get(source)! + 1));
      degree.set(target, degree.get(target)! - 1);
      if (degree.get(target) === 0) queue.push(target);
    }
  }
  const counts = new Map<number, number>();
  for (const node of nodes) {
    const column = rank.get(group.get(node.id)!) ?? 0;
    counts.set(column, (counts.get(column) ?? 0) + 1);
  }
  // Pack busy layers into two columns and center shorter layers to avoid tall sparse maps.
  const stride = Math.max(0, ...counts.values()) > 10 ? 660 : 370;
  const rows = new Map<number, number>();
  return [...nodes].sort((a, b) => a.file.localeCompare(b.file)).map((node) => {
    const column = rank.get(group.get(node.id)!) ?? 0;
    const row = rows.get(column) ?? 0;
    rows.set(column, row + 1);
    const columns = counts.get(column)! > 10 ? 2 : 1;
    const height = Math.ceil(counts.get(column)! / columns);
    return { id: node.id, position: { x: column * stride + (row % columns) * 285, y: (Math.floor(row / columns) - (height - 1) / 2) * 140 } };
  });
}
