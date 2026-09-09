import assert from "node:assert/strict";
import test from "node:test";
import { citationLabel, citationPage } from "../src/lib/qa.ts";
import { allowedRepositoryPath } from "../src/lib/proxy-policy.ts";

const id = "d8ad7614-0a30-4b7d-b499-1e1785be78bd";

test("citation navigation uses exact one-based source ranges at page boundaries", () => {
  assert.equal(citationPage(200), 0);
  assert.equal(citationPage(201), 1);
  assert.equal(citationPage(401), 2);
  assert.equal(citationLabel({ id: "S1", file_id: id, file_path: "auth.py", symbol: "login", start_line: 201, end_line: 250, source: "" }), "auth.py:201–250");
});

test("proxy allows only scoped Q&A operations and existing read routes", () => {
  assert.ok(allowedRepositoryPath([id, "ask"], "POST"));
  assert.ok(allowedRepositoryPath([id, "index"], "POST"));
  assert.ok(allowedRepositoryPath([id, "index"], "GET"));
  assert.ok(allowedRepositoryPath([id, "files", id], "GET"));
  assert.ok(allowedRepositoryPath([], "POST"));
  assert.equal(allowedRepositoryPath([id, "ask"], "GET"), false);
  assert.equal(allowedRepositoryPath([id, "files"], "POST"), false);
  assert.equal(allowedRepositoryPath(["..", "ask"], "POST"), false);
  assert.equal(allowedRepositoryPath([id, "index", "extra"], "POST"), false);
  assert.equal(allowedRepositoryPath([id, "index"], "DELETE"), false);
});
