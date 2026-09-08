import assert from "node:assert/strict";
import test from "node:test";
import { buildFileTree } from "../src/lib/file-tree.ts";
import { highlightSource } from "../src/lib/highlight.ts";
import { fetchFiles, request } from "../src/lib/repositories.ts";

test("file tree keeps duplicate basenames scoped and orders directories first", () => {
  const tree = buildFileTree([
    { id: "1", path: "z.py" }, { id: "2", path: "services/auth.py" },
    { id: "3", path: "routes/auth.py" }, { id: "4", path: "services/nested/item.ts" },
  ]);
  assert.deepEqual(tree.map((node) => node.name), ["routes", "services", "z.py"]);
  assert.equal(tree[0].children[0].fileId, "3");
  assert.equal(tree[1].children[1].fileId, "2");
  assert.equal(tree[1].children[0].children[0].path, "services/nested/item.ts");
});

test("source markup is escaped rather than rendered as repository HTML", () => {
  const source = 'const markup = "<img src=x onerror=alert(1)>";';
  const html = highlightSource(source, "javascript");
  assert.ok(html?.includes("&lt;img"));
  assert.ok(!html?.includes("<img"));
  assert.ok(html?.includes('class="hljs-'));
});

test("oversized highlight input falls back to plain code", () => {
  assert.equal(highlightSource("x".repeat(50_001), "python"), null);
  assert.equal(highlightSource("hello", "unsupported"), null);
});

test("file loader follows pagination instead of dropping files after the first page", async (context) => {
  const paths: string[] = [];
  context.mock.method(globalThis, "fetch", async (url: string) => {
    paths.push(url);
    return Response.json({ items: [{ id: paths.length, path: `file${paths.length}.py` }], total: 2 });
  });
  const result = await fetchFiles("snapshot", new AbortController().signal);
  assert.equal(result.length, 2);
  assert.ok(paths[1].endsWith("offset=1"));
});

test("client surfaces structured API failures", async (context) => {
  context.mock.method(globalThis, "fetch", async () => Response.json({ error: { message: "Database unavailable" } }, { status: 503 }));
  await assert.rejects(request(""), /Database unavailable/);
});
