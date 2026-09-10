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

## Milestone 4 — hybrid retrieval and diagnostics (2026-09-09)

- **128 backend tests passed**. New cases cover identifier/path matching, BM25, semantic-vs-hybrid recovery with synthetic vectors, deterministic ties, a 2,000-chunk collection, cycle-safe one-hop expansion, neighbors outside channel limits, preview without answer generation, preview/answer context parity, cross-snapshot isolation, invalid strategy/body limits, graph-limit fallback, JavaScript `$` identifiers, and comparison-harness mechanics. Existing ingestion, graph, citation, and migration tests pass.
- **14 frontend tests passed**. ESLint, TypeScript, the Next.js Webpack production build, Ruff lint/format, and `git diff --check` passed. Preview route restrictions and score display are covered. No dependencies or migrations were added; PostgreSQL `alembic check` remains clean.
- The 12-question offline experiment uses actual BM25 and explicit-match retrieval, with no embeddings or answer calls. It contains 14 chunks and two static import edges. Lexical Recall@1/3/6: **0.6111 / 0.8333 / 0.9167**. MRR@1/3/6: **0.7500 / 0.7917 / 0.8125**. Graph expansion produced the same aggregate metrics. Full per-question results: [evaluation-m4-offline.json](evaluation-m4-offline.json). These are curated fixture results, not a held-out benchmark or semantic-quality measurement.
- Live HTTP checks through the production frontend passed for the new POST preview route (correct `index_required` error on an unindexed snapshot), GET rejection, existing graph route, same-origin missing-key handling, and foreign-origin rejection.
- A temporary PostgreSQL fixture with an injected mock provider passed hybrid and semantic previews, exact-symbol diagnostics, answer citations/diagnostics, index replacement, and cascade cleanup. Only that unique test fixture was removed; existing user snapshots were preserved. The API and frontend run locally on ports 8000 and 3000.
- **No live embedding comparison or answer-faithfulness evaluation was run:** the server has no configured OpenAI key. The live harness is implemented, but its results remain unmeasured. No calibrated relevance threshold or confidence score is claimed.
- The browser runtime still reports an empty browser list. Visual interaction, hydration, keyboard navigation, and accessibility checks remain outstanding. The same two upstream Starlette/httpx and AnyIO deprecation warnings persist.

### Manual verification

1. Open a completed snapshot → **Ask**. Configure the server key and build an index if needed; existing Milestone 3 indexes can be reused.
2. Enter an exact function name, choose **Semantic baseline**, and select **Preview context**. Expand **Retrieved context** and inspect the scores and file links.
3. Repeat the same question with **Hybrid + dependencies**. Inspect keyword/exact-match signals and any rows marked **Dependency expansion**, including the adjacent file. Do not assume every question will improve.
4. Click a source link and verify the selected line range. Return to Ask; the preview remains labeled with its original question/mode.
5. Select **Ask** and compare the answer's citations with its own retrieved context. Preview uses only a query embedding; Ask makes a fresh retrieval and an answer-model call.
6. Run `python -m codeatlas.retrieval.evaluate --live` using the API virtual environment and inspect all three modes on the same questions. Record regressions as well as improvements before tuning weights or adding agent behavior.

## Milestone 5 — read-only investigations (2026-09-09)

- **146 backend tests passed**, including the existing suites and new agent behavior: model-selected reads, persisted traces/citations, rejected write/shell/URL actions, invented citations, failed/invalid/foreign-file reads, repeated-call and step limits, time/context/evidence/source budgets, sanitized provider faults, missing configuration, busy rejection, request limits, restart recovery, exact symbol lookup, semantic search, and dependency inspection.
- **16 frontend tests passed**. ESLint, TypeScript, the production Webpack build, Ruff lint/format, and `git diff --check` passed. Tests cover scoped run routes, rejection of mutation routes, terminal polling states, and counting failed read attempts.
- PostgreSQL was initially stopped after the environment resumed. Docker Desktop/PostgreSQL were restarted. Migration `0004` applied, and `alembic check` reported no pending model changes. SQLite tests also exercise full migration upgrade/downgrade and metadata comparison.
- A scripted provider behind a temporary real HTTP server verified asynchronous behavior: POST returned **202 before the model completed**, GET exposed a running trace step, a second run returned 409, and the completed run contained five trace entries and an exact cited source range.
- The same smoke fixture used real PostgreSQL to verify run persistence, final references without duplicated source, unchanged repository source, and cascade cleanup. Only the uniquely identified temporary fixture was removed; user snapshots were preserved. Startup recovery was disabled in that isolated test app so it could not alter runs owned by the production API.
- Production frontend proxy checks passed for run history/detail, same-origin missing-key handling, and foreign-origin rejection. The local API and frontend run on ports 8000 and 3000.
- **No live LLM investigation-quality result is claimed.** The server has no configured OpenAI key. Scripted-provider and mocked HTTP tests verify mechanics only.
- Browser runtime reconnection succeeded but returned an empty browser list. Visual/hydration/accessibility checks remain outstanding. Two upstream Starlette/httpx and AnyIO deprecation warnings remain. New mock-engine warnings were resolved by isolating startup recovery in health-only tests; recovery itself is tested against migrated databases.

### Manual verification

1. Run `alembic -c apps/api/alembic.ini upgrade head` using the API virtual environment, configure the existing server key, and restart the API with one worker.
2. Open a completed snapshot → **Agent**, and start a narrow investigation. Confirm that a plan and actual model/read steps appear as the run progresses.
3. Inspect exact symbol/file reads without a semantic index. Build an index in Ask and try a broader task that uses search; confirm that search appears as a remote embedding read.
4. Follow a finding's citation into source, return to Agent, and verify that the saved run remains accessible after reloading.
5. Ask for an operation outside read scope. The product has no mutation/execution tool; it should either report its limitation or fail a rejected decision, never alter source.
6. Stop/restart the API during a run and confirm that the run and pending step are marked interrupted/failed, with no automatic rerun. In-flight provider calls cannot currently be cancelled from the UI.
7. Review real-provider findings against expected evidence before making quality claims or enabling editing in a later milestone.

## Milestone 6 — reviewable source edits

- **171 backend tests passed**. New tests cover isolated/reversible edits, required current reads and SHA-256 preconditions, ambiguous replacements, traversal/absolute/Git/unsupported paths, case and directory collisions, byte/file limits, extra arguments, read-only mode rejection, persisted partial drafts, recovery after restart, cross-snapshot diff access, and mandatory review before successful completion.
- Unified patches were applied with Git in disposable test directories and checked for exact resulting bytes, including CRLF, Unicode separators within source, absent terminal newlines, new empty files, and emptied existing files. Product code never invokes Git or executes source.
- **18 frontend tests passed**, including the exact GET-only diff proxy route and diff-line classification. ESLint, TypeScript, Ruff lint/format, and the Next.js Webpack production build passed. Migration `0005` applied to PostgreSQL; `alembic check` found no pending changes. Existing SQLite migration/metadata tests also passed.
- A temporary real HTTP server with a scripted provider completed a read → edit → diff → finish run against PostgreSQL. Seven trace entries correctly distinguished the draft write. The stored overlay contained the edit, while original source remained byte-identical. The production frontend proxy served identical diff data and the run mode; rejected diff POST and foreign-origin requests; and returned the expected missing-key error for same-origin editing requests.
- Only the unique smoke-test snapshot and its cascading run were removed. Existing user snapshots were preserved.
- Patch download waits for the diff associated with the latest run status/trace, preventing download of a stale intermediate diff while the final fetch is pending. All drafts are labeled untested; partial results remain reviewable after failures or interruption.
- Browser runtime again returned no available browser. Visual interaction, hydration, patch-download interaction, keyboard behavior, and accessibility remain unverified. Live model editing quality remains unmeasured because no OpenAI key is configured. Scripted-provider tests establish application behavior, not generated-code correctness. The two existing upstream deprecation warnings remain.

### Manual verification

1. Apply migrations and configure the server provider key. Open a completed snapshot → Agent, choose **Propose edits (isolated draft)**, and submit a small request against a source file under 12 KB.
2. Verify that the public plan precedes writes, the trace identifies draft writes, and the diff updates as the run progresses. Download should be unavailable while the run is active.
3. After completion, inspect each changed file and download the patch. Compare against a separate full checkout at the displayed base SHA before applying it manually. Check new paths against files excluded during import.
4. Reopen the original file through the explorer or a citation and confirm its content is unchanged. Reload the page and verify the saved draft remains available.
5. Interrupt a run after a write, restart the API, and verify that the run is interrupted and its partial diff is preserved. No automatic rerun or apply occurs.
6. Start a read-only investigation and confirm its tool permissions remain unchanged. No mode exposes execution, automatic apply, or GitHub mutation.

## Milestone 7 — sandboxed tests (2026-09-10)

- **180 backend tests passed** in the default suite; six Docker tests are intentionally skipped unless opted in. New coverage includes explicit execution permission, profile schemas, fixed Docker arguments, scoped/versioned manual test requests, attempt and concurrency limits, source path/size restrictions, persisted stdout/stderr, recovery, sanitized errors, and agent fail → edit → retest behavior.
- **All six opt-in real Docker tests passed** (about 32 seconds). Python verified non-root UID, missing host environment sentinel/socket, blocked source/root writes, working bounded temporary storage, blocked outbound network, empty effective capabilities, no-new-privileges, active seccomp, and expected memory/PID limits. Node executed a TypeScript test. Other cases covered assertion failure, no tests, output flooding, the actual 30-second infinite-loop deadline, and no remaining test containers.
- **20 frontend tests passed**, including exact scoped GET/POST proxy permissions and selecting results only for the current workspace fingerprint. ESLint, TypeScript, Ruff lint/format, `git diff --check`, and the production Next.js Webpack build passed.
- Built both trusted runtime images from their digest-pinned Python 3.13 and Node 24 bases. No package/dependency installation was added to execution requests. PostgreSQL migration `0006` applied; Alembic reported no model drift. Existing SQLite upgrade/downgrade and metadata checks passed.
- A temporary real HTTP server used scripted decisions with **real PostgreSQL and Docker**. An initial unittest failed, the agent edited only its draft, and the second test passed. Test fingerprints differed, final diff matched the passing result, and original source remained byte-identical. The production frontend served test history and started a third manual test without an LLM key; that test passed. Stale fingerprint requests returned 409, a foreign origin returned 403, and a fourth attempt returned 422.
- Removed only the uniquely identified smoke snapshot and its cascading run/results. No managed test containers remained. Existing user snapshots were preserved. The local server execution setting is enabled after building the images; per-run/manual permission is still required. API readiness and the production frontend are available on ports 8000 and 3000.
- One new provider wire-format test initially used a draft response for a read-only schema. The fixture was corrected to return the exact requested argument fields; the test verifies that `run_tests` is offered only in explicitly authorized editing mode.
- Browser runtime again returned an empty browser list. Visual interaction, hydration, disclosure controls and accessibility remain unverified. No live-model repair-quality claim is made without a configured OpenAI key. Two upstream Starlette/httpx and AnyIO deprecation warnings remain.
- These results establish the implemented local Docker boundary and workflow, not proof against kernel/container-runtime vulnerabilities or malicious tests that forge a successful exit. Full-checkout dependency environments, public multi-tenant hardening, crash orphan cleanup, cancellation and durable jobs remain outside this milestone.

### Manual verification

1. Build the trusted images using the README commands, set `CODEATLAS_SANDBOX_ENABLED=true`, apply migrations, and restart the API with one worker. Keep Docker running locally.
2. Open a stopped draft → Agent → Proposed changes → Sandbox tests. Review the diff, choose a matching built-in profile, and select **Run tests in sandbox**. Observe running then final status, stdout/stderr, exit code, duration and workspace fingerprint. This flow requires no AI key.
3. For autonomous repairs, configure the provider key, start a new editing run, and explicitly choose the profile under **Agent test permission**. Use a small fixture with standard-library tests and a known fix. Confirm diff review precedes execution and the trace distinguishes execution from reads/writes.
4. Inspect a failing result followed by an edit/retest. Earlier-draft results must remain labeled; a successful agent finish must not conceal failing test results. Three test attempts exhaust the shared manual/agent budget.
5. Run the opt-in Docker suite with `CODEATLAS_TEST_DOCKER=1 apps/api/.venv/bin/pytest apps/api/tests/test_sandbox_live.py -q`. It includes an intentional 30-second timeout. Never execute those fixture programs directly on the host.

## Architecture UI refresh (2026-09-10)

- Added a dependency-map heading, snapshot summary cards, directory shortcuts, overview/neighborhood controls, reset layout, fit-map/find-selection actions, and an optional language-colored minimap.
- Redesigned file cards with language badges, clearer filename/path hierarchy, parser-warning markers, and visible-link counts. Selected-file connections are emphasized while unrelated content is subdued. The inspector now uses compact metadata and collapsible imports/dependents/unresolved sections.
- Dense graph layers pack into two columns; shorter layers are centered. A regression test verifies that card rectangles do not overlap, import direction remains left-to-right across layers, and positions are deterministic. Existing graph filters and the 200-node limit remain covered.
- **21 frontend tests passed**, plus ESLint, TypeScript, the production Webpack build, and `git diff --check`. No backend schema or dependency changes.
- Browser selection and documented connection troubleshooting still found no available browser. Visual appearance, keyboard interactions and responsive rendering remain unverified in a live browser.
- Confirmed locally without printing credentials: provider integration exists, but no OpenAI API key is configured. Configured model names are `gpt-4.1-mini` for answers/agent decisions and `text-embedding-3-small` for retrieval embeddings. The architecture map itself uses deterministic static analysis.

## Claude provider checkpoint — 2026-09-10

- Claude is now the default reasoning provider (`claude-sonnet-5`); OpenAI reasoning remains an explicit configuration option. OpenAI embeddings retain their existing fingerprint and separate credential.
- Existing backend suite: **180 passed, 6 opt-in Docker tests skipped**. New Claude suite: **16 passed**, covering host/credential separation, provider selection, permission-specific schemas, refusal/truncation/malformed response rejection, sanitized provider errors, independent availability, and a mocked Claude-to-runtime source-read/cited-finish flow with persisted model identity.
- Ruff lint/format, frontend lint/type checks, **21 frontend tests**, production build, and `git diff --check` passed. Local API and frontend restarted with no active runs/tests; HTTP checks through the frontend proxy verified Claude model/configuration status.
- No live Claude calls were made: the Anthropic key is not configured. No claim of live answer/edit quality or browser visual verification. Existing upstream test deprecation warnings remain.
- MCP client/server connections are a design proposal in `mcp-architecture.md`, not an implemented or interoperability-tested capability.

## MCP read transport checkpoint — 2026-09-10

- Official MCP Python SDK 2.2.0 installed and locked with its dependencies; dependency consistency check passed. Bundled client/server negotiate protocol 2026-07-28. No new public HTTP endpoint.
- Full backend suite: **201 passed, 6 opt-in Docker tests skipped**. After adding the discovery-rejection test, the focused MCP suite passed **6 tests** (202 backend tests in total across the checked suites). These cover actual stdio agent execution, discovery, strict arguments, cross-repository rejection, malformed/forged evidence, evidence ID remapping, failure traces without fallback, and timeout/process cleanup.
- A read-only check against the existing local PostgreSQL database passed file listing and source reading through the actual stdio client/server, including citation verification. No snapshot source was changed. The child received only the database URL as application-specific environment configuration.
- Frontend lint, type checking, **21 tests**, and production build passed. Ruff lint/format and diff whitespace checks passed. Trace UI now labels MCP reads. No browser visual verification or live Claude-quality result is claimed.
- MCP is enabled in the ignored local environment and `.env.example`; the Settings fallback stays local. Remote servers, external-host interoperability, MCP edits/testing, and Git writes remain unimplemented. One pre-existing upstream AnyIO test warning remains.
