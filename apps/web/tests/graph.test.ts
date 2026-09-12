import assert from "node:assert/strict";
import test from "node:test";
import { layoutGraph, visibleGraph, type DependencyGraph, type GraphEdge, type GraphNode } from "../src/lib/graph.ts";

function node(id: string, language = "typescript"): GraphNode {
  return { id, label: id, type: "file", file: `src/${id}`, language, symbol_count: 1, warning: null };
}
function edge(source: string, target: string): GraphEdge {
  return { id: `${source}:${target}`, source, target, relationship: "imports", in_cycle: false, evidence: [] };
}
function graph(nodes: GraphNode[], edges: GraphEdge[], cycles: string[][] = []): DependencyGraph {
  return { repository_id: "repo", nodes, edges, cycles, notes: [], unresolved: [], legacy_files: 0 };
}

test("focus includes direct imports and dependents, excluding unrelated files", () => {
  const data = graph([node("a"), node("b"), node("c"), node("d")], [edge("a", "b"), edge("c", "a"), edge("b", "d")]);
  const visible = visibleGraph(data, "", "", "a");
  assert.deepEqual(visible.nodes.map((item) => item.id), ["a", "b", "c"]);
  assert.deepEqual(visible.edges.map((item) => item.id), ["a:b", "c:a"]);
});

test("filters and canvas cap expose the omitted count without dangling edges", () => {
  const nodes = Array.from({ length: 250 }, (_, index) => node(`file-${index}`));
  const data = graph(nodes, [edge("file-0", "file-249")]);
  const visible = visibleGraph(data, "", "", null, 200, true);
  assert.equal(visible.total, 250);
  assert.equal(visible.nodes.length, 200);
  const ids = new Set(visible.nodes.map((item) => item.id));
  assert.ok(visible.edges.every((item) => ids.has(item.source) && ids.has(item.target)));
  assert.equal(visibleGraph(data, "missing", "", null).nodes.length, 0);
  assert.equal(visibleGraph(data, "", "python", null).nodes.length, 0);
});

test("layout puts importers before dependencies with unique stable positions", () => {
  const nodes = [node("c"), node("b"), node("a")];
  const edges = [edge("a", "b"), edge("b", "c")];
  const layout = layoutGraph(nodes, edges, []);
  const positions = new Map(layout.map((item) => [item.id, item.position]));
  assert.ok(positions.get("a")!.x < positions.get("b")!.x);
  assert.ok(positions.get("b")!.x < positions.get("c")!.x);
  assert.deepEqual(layoutGraph([...nodes].reverse(), [...edges].reverse(), []), layout);
});

test("cycles share a layer without overlap or infinite traversal", () => {
  const nodes = [node("a"), node("b"), node("c")];
  const layout = layoutGraph(nodes, [edge("a", "b"), edge("b", "a"), edge("b", "c")], [["a", "b"]]);
  assert.equal(layout[0].position.x, layout[1].position.x);
  assert.notEqual(layout[0].position.y, layout[1].position.y);
  assert.ok(layout[2].position.x > layout[0].position.x);
  assert.deepEqual(layoutGraph([], [], []), []);
});

test("dense layers pack without overlapping cards or reversing import direction", () => {
  const sources = Array.from({ length: 24 }, (_, index) => node(`source-${index}`));
  const nodes = [...sources, node("shared")];
  const edges = sources.map((source) => edge(source.id, "shared"));
  const layout = layoutGraph(nodes, edges, []);
  const sink = layout.find((item) => item.id === "shared")!;
  assert.ok(layout.filter((item) => item.id !== "shared").every((item) => item.position.x < sink.position.x));
  for (let i = 0; i < layout.length; i++) for (let j = i + 1; j < layout.length; j++) {
    const a = layout[i].position, b = layout[j].position;
    assert.ok(Math.abs(a.x - b.x) >= 250 || Math.abs(a.y - b.y) >= 110, "file cards must not overlap");
  }
  const ys = layout.map((item) => item.position.y);
  assert.ok(Math.max(...ys) - Math.min(...ys) < 2000, "a dense layer should not become one tall stack");
  assert.deepEqual(layoutGraph([...nodes].reverse(), [...edges].reverse(), []), layout);
});


test("unconnected files are hidden per view and can be restored without hiding incoming-only nodes", () => {
  const nodes = [node("producer"), node("consumer"), node("alone"), node("self")];
  for (const relationship of ["imports", "data_flow"] as const) {
    const links = [edge("producer", "consumer"), edge("self", "self")].map((item) => ({ ...item, relationship }));
    const data = graph(nodes, links);
    const connected = visibleGraph(data, "", "", null);
    assert.deepEqual(connected.nodes.map((item) => item.id), ["consumer", "producer"]);
    assert.equal(connected.unconnectedCount, 2);
    assert.equal(connected.edges.length, 1);
    const all = visibleGraph(data, "", "", null, 200, true);
    assert.equal(all.nodes.length, 4);
    assert.equal(all.edges.length, 2);
    assert.equal(visibleGraph(data, "alone", "", null).total, 0);
    assert.equal(visibleGraph(data, "alone", "", null, 200, true).total, 1);
  }
  assert.equal(visibleGraph(graph(nodes, []), "", "", null).nodes.length, 0);
  assert.equal(visibleGraph(graph(nodes, []), "", "", null, 200, true).nodes.length, 4);
});
