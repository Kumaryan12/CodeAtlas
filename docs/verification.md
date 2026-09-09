# Verification record

## Milestone 2 — 2026-09-09

| Check | Result |
| --- | --- |
| Backend pytest | 92 passed; two existing upstream deprecation warnings |
| Ruff lint and formatting | Passed |
| Frontend node:test | 10 passed |
| Frontend lint and TypeScript | Passed |
| Next.js production build | Passed with React Flow and its stylesheet |
| PostgreSQL migration `0002` | Applied successfully; Alembic schema comparison reports no pending operations |
| Real GitHub import through production proxy | CodeAtlas at `a1dc141`, 63 eligible source files, structured import references and alias config persisted |
| Fresh snapshot graph through Next.js | 63 nodes, 88 local import edges, 143 unresolved observations, 0 cycle groups; no legacy files |
| Alias evidence | `typescript_paths` edges present with statement lines from captured tsconfig |
| Existing CodeAtlas snapshot | 53 nodes and 55 edges; legacy coverage warning present; source unchanged |
| Existing namespace-package snapshot | 57 nodes and 44 edges after scoped namespace resolution; legacy metadata remains readable |
| Graph-to-source API navigation | Edge target IDs retrieve the corresponding persisted source and symbols |
| Graph queries | Regression test proves source text is not selected |

The API exposes only local indexed-file edges. The 143 unresolved observations include standard-library and third-party imports, missing indexed targets and unsupported resolver cases; this is not a count of application errors.

### Coverage added

- Python absolute, relative, parent-relative, named submodule, regular-package, src-layout and namespace-package imports.
- JS/TS relative files, directory index files, re-exports, TypeScript extension candidates, path-alias precedence/fallback, nearest configuration and base URL.
- Ambiguous modules, unresolved packages, path escapes, unsupported configuration and config scan limits.
- Deduplicated edges with import evidence, isolated files, self-cycles, SCC groups and a 2,000-node cycle without recursion.
- Legacy imports, snapshot scoping, failed-snapshot rejection, and a persisted API fixture combining Python cycles and TypeScript alias edges.
- Frontend layout determinism, cycle layout, direct-neighborhood filtering, language/path filtering and a 200-node cap with no dangling edges.

### Findings and fixes

Live testing of an existing namespace-package snapshot revealed that relying on `__init__.py` and conventional src roots missed `backend/app` layouts. Added bounded qualified-namespace inference. Inspecting its cycle output then caught an overly broad bare-module root: a nested `logging.py` importing standard-library `logging` was incorrectly treated as a self-import. Removed per-file-directory inference and added a targeted regression. The final live graph has no such false cycle. Inferred roots remain explicitly labelled; this is not full runtime import resolution.

Migration `0002` preserves old snapshots rather than parsing or downloading during migration. Tests run the real migration upgrade/downgrade/schema comparison, and live PostgreSQL retained both previous source snapshots and their new legacy graph views.

### Remaining verification limits

Browser discovery again returned no connected browser. React Flow pointer/keyboard interactions, visual spacing, fit-view behavior, mobile layout and accessibility have not been exercised in a browser. The graph data, layout/filter logic, production build and live proxy/source navigation were tested. Use the Architecture walkthrough in the README for manual visual verification.

No browser performance benchmark or hosted multi-user load test was run. Config JSONC/inheritance, package exports, arbitrary Python execution environments, CommonJS/dynamic imports and call graphs remain outside this milestone.

---

## Milestone 1 — 2026-09-09

| Check | Result |
| --- | --- |
| Backend pytest suite | 67 passed; two upstream deprecation warnings |
| Python Ruff lint and formatting | Passed |
| Frontend node:test suite | 6 passed |
| Frontend ESLint and TypeScript | Passed |
| Next.js production build | Passed with Webpack |
| PostgreSQL Compose service | Started and healthy |
| Alembic upgrade | Applied `0001` successfully to PostgreSQL; rerun was safe |
| Alembic live schema comparison | No new upgrade operations detected |
| Database readiness | HTTP 200 with `database=connected` |
| Actual GitHub import through FastAPI | CodeAtlas at `0bb4fb1`: 41 files, 126 symbols, no parser warnings |
| Actual same-origin import through Next.js | CodeAtlas at `83ff08d`: 53 files, 159 symbols, one parser warning |
| Snapshot persistence | Original snapshot remained available after API and PostgreSQL restarts |
| Source/symbol proxy | Source text and `create_app` symbol locations returned from persisted snapshot |
| Symbol pagination | Page size and total matched persisted symbol count |
| Invalid repository URL through frontend | Structured HTTP 422 |
| Foreign browser Origin | Structured HTTP 403 |
| Oversized import JSON | Structured HTTP 413 |
| Workspace cleanup | Fixture imports and handled failures removed temporary directories |

The current-commit import had 34 Python, 16 TypeScript and 3 JavaScript files. Its one warning came from a **valid** TSX text node containing a bare ampersand (`JavaScript & TypeScript`), which the current Tree-sitter grammar flags even though Next.js compiles it. The application correctly kept source and extracted symbols available, marked the snapshot `partial`, and reported the file warning. Parser diagnostics are intentionally preserved rather than hidden; they are not treated as a definitive compiler verdict.

### Automated coverage

- GitHub URL normalization and rejection of arbitrary schemes, hosts, credentials, ports, traversal encodings, fragments and subpaths.
- Fixed-host, commit-pinned download requests, stream limits, private/missing repositories, redirects and upstream errors.
- Hostile archive paths, links, special entries, case collisions, gzip expansion limits, file/entry/source/symbol limits, unsupported encodings, binary/generated files and ignored directories.
- Python nesting, methods, parameters and line ranges; JS/TS declarations, arrows, interfaces, types, JSX/TSX and malformed syntax.
- Actual trusted parser subprocess and controlled timeout response; source-execution sentinel remains absent.
- Actual migration upgrade/schema comparison/downgrade/re-upgrade on ephemeral SQLite with foreign keys enabled.
- API import, partial results, failed imports, database rollback, snapshot/file ownership, pagination, request limits, concurrency rejection, cleanup, and source-free summary queries.
- Frontend file-tree structure, escaped source markup, highlighting fallback, multi-page file loading, API errors and loopback-origin regression.

### Issues found and resolved

- The formatter changed the exact-location Python fixture. Restored the fixture and excluded parser fixtures from formatting.
- Frontend lint rejected an unnecessary memoization; simplified the bounded highlighting call.
- Live HTTP testing found that Next.js normalized the request URL host to `localhost`, incorrectly rejecting a browser using `127.0.0.1`. The origin guard now compares against the actual Host header, with regression coverage and live 422/403/413/201 verification.
- Initial per-file persistence was replaced with transactional bulk inserts; the database rollback test and real PostgreSQL import both passed afterward.
- Summary queries initially loaded full file source, including repeated source rows in the symbol join. Narrowed projections with deferred-column access guards prevent that amplification; a SQL-level regression test checks that source/import payloads are never selected by either summary route.
- A usage-limit approval interruption stopped one server-inspection attempt. After the user continued with updated permissions, services were restarted and all final checks rerun.

### Remaining verification limits

No browser was connected to the browser tool. Visual layout, hydration, pointer/keyboard interaction, mobile layout and accessibility have **not** been verified in a browser. Production HTML, proxy behavior, unit tests and build checks passed. Follow the manual steps in the README to finish visual verification.

No load test, hosted security review, native-parser sandbox test, or multi-worker deployment validation was performed. The single-worker and parser-process limitations are documented. Backend tests still emit upstream Starlette/httpx and AnyIO deprecation warnings.

---

## Milestone 0 — historical verification

Verified on 2026-09-08 using Node 26.0.0, npm 11.12.1, Python 3.14.7, Next.js 16.3.4 and FastAPI 0.141.1 on macOS.

| Check | Result |
| --- | --- |
| `pytest apps/api/tests -q` through project virtual environment | 5 passed |
| Ruff lint and format checks | Passed |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm run build` (Webpack) | Passed; page prerendered and health route dynamic |
| `npm start` | Started successfully on 127.0.0.1:3000 |
| Uvicorn startup | Started successfully on 127.0.0.1:8000 |
| Production page HTTP check | 200; expected empty-state content present; database password absent |
| FastAPI `/api/health` | 200 with expected service identity |
| Next.js `/api/health`, API running | 200; successfully contacted FastAPI |
| Next.js `/api/health`, API stopped | 503 with sanitized `api_unavailable` error |
| OpenAPI schema | Both health endpoints present |
| FastAPI `/api/ready`, PostgreSQL unavailable | 503 with sanitized structured error |
| Compose configuration | Validated successfully |
| npm install audit | Zero reported vulnerabilities |
| Git hygiene | `.env`, virtual environment and node_modules ignored; diff whitespace check passed |

## Failures resolved

- Initial frontend lint errors were corrected: use Next.js Link for local navigation, a named PostCSS configuration, and asynchronous status updates in the health effect.
- ESLint 10 was incompatible with the installed React lint plugin. ESLint 9 was restored and lint passed; its upstream end-of-support warning is documented tooling debt.
- Turbopack failed to bind a CSS worker port in this managed environment. The scripts now use Webpack, which built successfully.
- Sandbox restrictions initially prevented local server startup and HTTP access. Retrying with approved elevated tool execution allowed both services and HTTP checks to run.

## Remaining verification limitations

- Docker is installed but its daemon is stopped. No PostgreSQL container was launched, and real database readiness success was not verified. The readiness success branch is unit-tested with the database boundary mocked. Run `docker compose up -d postgres`, then request `/api/ready` to complete that integration check.
- Browser discovery returned no available browsers. Rendered layout, responsiveness, hydration, keyboard behavior, and the refresh interaction were not visually verified. The production page and proxy were checked over HTTP only; manual browser steps are in the README.
- Backend tests emit two upstream deprecation warnings concerning Starlette/httpx and AnyIO. They are visible and do not fail the tests.

This record describes local verification, not a production-readiness certification.

## Milestone 3 — repository Q&A (2026-09-09)

- **115 backend tests passed**, including real Alembic migration upgrade/downgrade and metadata comparison on SQLite; symbol-boundary chunking; exact line ranges including Unicode separators inside source strings; normalized cosine ranking; malformed/nonfinite/zero vectors; snapshot isolation; idempotent indexing; stale model detection; preservation after embedding failure; citation validation; abstention; request limits; provider authentication/rate-limit failures; incomplete output; and wire-format tests with mock HTTP responses.
- **12 frontend tests passed**, covering existing explorer/graph behavior plus source-page boundaries and the proxy's method/path allowlist. ESLint, TypeScript, and the Next.js Webpack production build passed.
- Ruff lint and formatting passed. `git diff --check` passed. No new package dependencies were introduced.
- PostgreSQL migrated to `0003`; `alembic check` reported no pending model changes. A temporary, uniquely identified fixture exercised persisted indexing, a cited answer, successful replacement after an embedding-model change, and cascade cleanup against real PostgreSQL. This used an injected mock provider. Only that temporary fixture was removed; user snapshots were preserved.
- Live Next.js/API HTTP checks passed: root page, index status through the frontend proxy, `ai_not_configured` response with the real same-origin header, rejection of foreign-origin questions, and an existing snapshot's dependency graph.
- The API and production frontend were restarted locally on ports 8000 and 3000. An initial start command redundantly forwarded a hostname and failed; the repository's normal `npm start` command succeeded.
- No server OpenAI key is configured. The evaluation CLI exits with a sanitized `ai_not_configured` message. **No live embeddings, generated answers, Recall@K/MRR result, or answer-faithfulness score has been verified.** Synthetic test vectors validate software mechanics only.
- Browser runtime reports no available browser. Interactive visual/hydration/accessibility verification remains outstanding. HTTP responses and builds are not a replacement for browser verification.
- The same two upstream Starlette/httpx and AnyIO deprecation warnings remain; they do not fail tests.

### Manual verification

1. Preserve `.env`, add `CODEATLAS_OPENAI_API_KEY`, and restart the API. Run migration `upgrade head` when updating an existing checkout.
2. Open a ready/partial repository snapshot and select **Ask**. Without a key, confirm that setup guidance appears and question submission is disabled.
3. With a key configured, build the semantic index. Verify the excerpt count and any skipped oversized-line warning; a second index POST should reuse the index.
4. Ask a question naming a known behavior or function. Open a citation, verify its line range against the source, then return to Ask and confirm the answer remains.
5. Ask about behavior absent from the repository. Inspect evidence and abstention behavior; valid references alone are not proof that an answer is faithful.
6. Change `CODEATLAS_EMBEDDING_MODEL`, restart, and verify the index is marked stale and requires rebuilding. Failed rebuilds should preserve the previous model's complete index.
7. Run `apps/api/.venv/bin/python -m codeatlas.retrieval.evaluate --live` and retain the JSON results as the initial real-embedding baseline. Review answers manually before claiming Q&A quality.
