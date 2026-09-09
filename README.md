# CodeAtlas

**Codebase intelligence, grounded in source.** Import a public GitHub repository and explore a commit-pinned snapshot of its Python, JavaScript, and TypeScript files, functions, classes, methods, and imports.

**Current milestone: 4 — hybrid retrieval and diagnostics.** Importing and exploring code requires no AI key. Optional semantic indexing and cited answers use a server-configured OpenAI key. Autonomous engineering remains a future milestone.

## What works

- Public GitHub URL validation, metadata lookup, default-branch commit resolution, and bounded archive downloads.
- Isolated temporary workspaces, archive validation, file/language detection, skip statistics, and automatic cleanup.
- Python AST and JavaScript/TypeScript Tree-sitter parsing, including JSX/TSX, symbol parameters, parent relationships, and exact line ranges.
- PostgreSQL snapshot persistence with Alembic migrations, transactional bulk writes, and recorded import failures.
- Repository selection, searchable file tree, syntax-highlighted code, symbol navigation, file statistics, and parser warnings.
- React Flow architecture view with resolved imports, dependency inspection, cycle highlighting, filtering, and source navigation.
- Symbol-first semantic indexing, snapshot-scoped hybrid retrieval, an AI provider interface, and an Ask view with clickable source citations.
- Semantic/keyword/exact-symbol rank fusion, bounded import expansion, context previews, and per-excerpt retrieval diagnostics.
- Typed REST endpoints, structured ingestion logs, health/readiness checks, automated behavior tests, and local PostgreSQL Compose configuration.

## Quick start

Prerequisites: Node.js 22.13+, npm, Python 3.12+, Docker Desktop or a running Docker daemon with Compose. Development is verified on macOS with Node 26 and Python 3.14. Use one API worker for this synchronous MVP.

From the project root, on first setup:

```sh
cp .env.example .env
npm ci
python3 -m venv apps/api/.venv
apps/api/.venv/bin/python -m pip install -r apps/api/requirements-dev.lock
apps/api/.venv/bin/python -m pip install --no-deps -e apps/api
```

Preserve an existing `.env` when updating the project. Start Docker, then:

```sh
docker compose up -d --wait postgres
apps/api/.venv/bin/alembic -c apps/api/alembic.ini upgrade head
```

Terminal 1:

```sh
apps/api/.venv/bin/uvicorn codeatlas.main:app --app-dir apps/api --reload --host 127.0.0.1 --port 8000
```

Terminal 2:

```sh
npm run dev
```

Open **http://127.0.0.1:3000** and import `https://github.com/Kumaryan12/CodeAtlas`. For interactive API docs, open http://127.0.0.1:8000/docs.

Each import creates a new snapshot, even for a previously imported URL. It resolves the current default branch to a commit before downloading. Existing snapshots do not change when GitHub changes.

The API and frontend can start without PostgreSQL, but imports and repository browsing require a reachable, migrated database. `/api/health` reports process liveness; `/api/ready` checks database connectivity, not migration currency. Use `alembic check` separately to check schema agreement.

For a production-mode local frontend smoke test: `npm run build && npm start`. Authentication and deployment hardening are not included; keep this development application on loopback.

## Using the workspace

1. Enter a public repository root URL. Keep the page open while the synchronous import runs.
2. Select a snapshot in the sidebar. Its branch, pinned commit, status, and source statistics appear above the explorer.
3. Expand directories or filter by path; select a file to read source and inspect symbols.
4. Select a symbol to jump to its source page and highlight its line-number range. Code is paginated at 200 lines to bound rendering work.
5. Review scan details for skipped files and parser warnings. Language percentages use indexed file counts, not lines of code.
6. Use the sidebar refresh control to reload snapshots. Failed imports retain a useful error; re-enter the URL to create another attempt.

A snapshot with malformed source is marked `partial`; unaffected files and readable source remain available. A valid repository with no supported source files produces an explicit empty state, not an import error.

## Exploring architecture

Select **Architecture** beside **Code** after choosing a completed snapshot.

- Drag nodes, pan, zoom, use the fit-view control, or navigate with the minimap.
- An arrow points from the importing file to its dependency. Amber edges belong to a cycle group; dashed edges use inferred Python roots.
- Select a node to inspect its path, language, symbol count, outgoing imports, incoming dependents, and unresolved imports with reasons and statement lines.
- Choose **Open source & symbols** to return to the existing code viewer for that file.
- Filter by path/language or enable **Selected file + direct neighbors**. The canvas displays at most 200 matching files, with an explicit visible/total count. The API returns the full bounded graph.

Old snapshots still work, but their import strings lack statement lines and Python imported names, and they have no captured alias configuration. The graph labels this as legacy coverage. **Reimport a repository for complete Milestone 2 metadata; migrations do not redownload or rewrite existing source.**

The graph resolves Python relative imports and named submodules, inferred package/namespace roots, JS/TS relative and `index` entry files, `.js`-to-TypeScript source candidates, and a strict-JSON subset of `tsconfig.json`/`jsconfig.json` `paths` and `baseUrl`. Config inheritance, project references, JSONC comments, package.json exports, installed packages, dynamic imports, and full compiler/runtime resolution are not implemented. Unsupported configuration produces a visible note. When multiple files could match, the graph reports ambiguity instead of guessing.

External packages and otherwise unresolved bare specifiers are labelled `external_or_unresolved`; the graph does not pretend to distinguish them without environment information. A missing local module means no eligible indexed source matched—it can also refer to a skipped asset. Cycle groups are strongly connected components, not an enumeration of every possible cycle.

Limits: 50,000 import observations plus Python imported names, 50,000 local edges, up to 64 alias configs (128 KiB each / 1 MiB aggregate), 64 alias patterns per config and 16 fallback targets per pattern. Python namespace inference considers at most the last 32 path components. Relative/config paths are normalized within the snapshot and never used for filesystem or network access.

## Architecture

```text
Browser → Next.js workspace / fixed same-origin proxy → FastAPI
                                                        │
               GitHub metadata → commit-pinned archive ──┤
                                                        ↓
                      bounded temporary workspace → trusted parser subprocess
                                                        ↓
                           scan results → transactional PostgreSQL snapshot
```

Source is stored once per file. Symbols store names, types, parameters, parent IDs, and line ranges; source snippets can be derived from the file without duplicating class/function bodies. Structured imports and captured alias configuration feed a deterministic, on-demand file graph; graph reads do not load source text or invoke parsers. Edges describe static imports, not function calls or runtime execution.

See [development guide](docs/development.md) for architecture trade-offs and interview questions, [source tree](docs/structure.md), and [verification record](docs/verification.md).

## Configuration

Root `.env` is read by Compose, FastAPI, and Next.js configuration. Restart services after changes. Never commit it.

| Variable | Purpose |
| --- | --- |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Local PostgreSQL initialization |
| `POSTGRES_PORT` | Host database port, default 5432 |
| `CODEATLAS_DATABASE_URL` | SQLAlchemy PostgreSQL URL using the psycopg driver |
| `API_BASE_URL` | Server-only Next.js upstream API address |
| `CODEATLAS_WORKSPACE_ROOT` | Optional absolute temporary-workspace root; defaults to project `workspaces/` |
| `CODEATLAS_MAX_DOWNLOAD_BYTES` | Compressed archive limit; default 20 MiB |
| `CODEATLAS_DOWNLOAD_TIMEOUT_SECONDS` | Download deadline; default 45 seconds, maximum 60 |
| `CODEATLAS_ANALYSIS_TIMEOUT_SECONDS` | Hard parser-subprocess timeout; default/maximum 60 seconds |

Update `CODEATLAS_DATABASE_URL` too if you change database credentials or the host port. Compose initialization variables only apply to a new data volume; changing `.env` does not change an existing database password. Example credentials are for local development only.

The Python lock file pins the tested development environment, including transitive packages; it is a pip version snapshot, not a cross-platform hash lock. For deliberate upgrades, install `-e 'apps/api[dev]'`, rerun checks, and regenerate using `apps/api/.venv/bin/python -m pip freeze --exclude codeatlas-api`.

## REST API

| Route | Behavior |
| --- | --- |
| `POST /api/repositories` | JSON `{ "url": "https://github.com/owner/repo" }`; 201 on completed analysis |
| `GET /api/repositories` | Paginated snapshots; `limit` defaults to 50, max 100; `offset` supported |
| `GET /api/repositories/{id}` | Snapshot metadata, state, statistics, and error |
| `GET /api/repositories/{id}/files` | Source-file summaries; `limit` defaults to/max 1000; `offset` supported |
| `GET /api/repositories/{id}/files/{file_id}` | Full source, imports, warnings, and file symbols |
| `GET /api/repositories/{id}/graph` | File nodes, local import edges with evidence, unresolved observations, cycle groups and coverage notes |
| `GET /api/repositories/{id}/symbols` | Located symbols; optional `file_id`; `limit` defaults to 200, max 1000; `offset` supported |
| `GET /api/health` | 200 liveness, no database access |
| `GET /api/ready` | 200 after `SELECT 1`; sanitized 503 on database failure |
| `GET /docs`, `GET /openapi.json` | Interactive documentation and machine-readable schema |

List responses contain `{ "items": [...], "total": N }`. Application errors use `{ "error": { "code": "...", "message": "..." } }`. Invalid parameters return 422; unavailable repositories 404; concurrent imports 409; size violations 413; upstream refusal/rate limits 429; network/upstream failures 502; database failures 503; timeouts 504.

## Security boundaries and limits

Repository code is never executed, imported, installed, or tested. Only the trusted CodeAtlas parser runs, via a fixed subprocess command with isolated Python imports and a minimal environment. This process boundary provides timeout enforcement; it is **not an OS security sandbox** for native-parser vulnerabilities.

- Only HTTPS `github.com/owner/repo` roots are accepted. No credentials, ports, query strings, fragments, subpaths, arbitrary hosts, or redirects.
- Network requests use fixed GitHub API/codeload hosts, no environment proxy/credentials, bounded streams, and timeouts.
- Before tar parsing, gzip expansion is bounded to **100 MiB**, including extended headers. Archive entries are capped at **10,000**.
- Absolute paths, traversal, backslashes, control characters, duplicate/case-colliding paths, links, sparse files, and special entries reject the archive. No archive paths are extracted onto disk.
- Supported individual source files are capped at **512 KiB**; aggregate source at **10 MiB**; symbols at **20,000**. Oversized individual files are skipped; aggregate limits reject the import.
- Generated files, binaries, unsupported encodings/types, and common dependency/build directories are skipped with counts. Source must be UTF-8; these are explicit heuristics, not a complete `.gitignore` interpreter.
- Repository POST JSON is capped at **4 KiB** in both services. The frontend rejects browser requests from other origins and forwards only allowed repository routes.
- Temporary workspaces are removed after normal completion or handled failures. Persisted source is returned by repository/file IDs, never user-provided filesystem paths.
- Logs contain event names, snapshot IDs, status/error codes, and duration; raw code, credentials, and raw exception text are excluded from application ingestion logs.

## Known limitations

- Local, single-user application with **one synchronous import per API process**. Use one worker. No durable queue, cross-process concurrency control, total storage quota, or cancellation yet. A disconnected client does not cancel the import.
- If the API is killed mid-import or the database stays unavailable, a snapshot may remain `importing`; refresh before retrying. There is no automatic crash recovery or orphan-workspace scavenger yet. A new import creates a separate snapshot.
- Public default branches only; no private-repository authentication, arbitrary branch selection, repository history, submodules, or Git LFS content. Unauthenticated GitHub limits apply; moved repositories require their current URL. Commit metadata is bounded to 2 MB and repository metadata to 1 MB.
- The file tree shows eligible source files, not every repository asset. Symlinks anywhere in an archive cause rejection, even when a legitimate repository uses them.
- Symbol extraction is basic static analysis. Tree-sitter warnings are parser diagnostics, not proof of invalid code: valid JSX text containing a bare `&` can trigger a warning in the current grammar. Python uses the running interpreter's grammar. JS/TS covers named declarations, assigned functions/arrows/classes, class methods, interfaces and type aliases; anonymous exports, overload semantics, dynamic behavior, and complete call resolution are not modeled.
- Import strings are Python static imports and JS/TS static import/re-export paths; CommonJS/dynamic import resolution is deferred; static import edges are supported.
- Browser visual verification was unavailable in this environment. Unit tests, production builds, and live HTTP checks do not replace visual/hydration/accessibility testing.

## Repository Q&A

1. Add `CODEATLAS_OPENAI_API_KEY` to your existing root `.env` and restart the API. Do not put the key in browser code or a `NEXT_PUBLIC_` variable.
2. Open a ready or partial snapshot at [localhost:3000](http://localhost:3000), select **Ask**, then **Build semantic index**. Existing snapshots work without reimporting.
3. Choose **Hybrid + dependencies** or **Semantic baseline**. Use **Preview context** to inspect retrieval before generating an answer. Preview makes one query-embedding call and no answer-model call.
4. Ask a specific implementation question. Click a cited path to open its exact source range; return to Ask to retain the answer. Expand **Inspect supporting excerpts** to review the actual context.

Indexing sends eligible source excerpts to OpenAI's embedding endpoint and stores vectors locally. Answer generation sends the question and at most six retrieved excerpts; it does not send the entire repository. Usage may incur provider charges. The default models are `text-embedding-3-small` and `gpt-4.1-mini`, configurable through `CODEATLAS_EMBEDDING_MODEL` and `CODEATLAS_ANSWER_MODEL`. Changing the embedding model makes existing indexes stale and requires rebuilding; changing the answer model does not.

| Route under `/api/repositories/{id}` | Behavior |
| --- | --- |
| `GET /index` | Configuration availability and index state: not indexed, ready, or stale |
| `POST /index` with `{}` | Build a complete index; reuse an index with the same fingerprint |
| `POST /ask` with `{"question":"How does login work?","strategy":"hybrid"}` | Cited answer plus retrieval diagnostics |
| `POST /retrieve` with the same question/strategy body | Preview up to six retrieved excerpts without generating an answer |

Function/method/class boundaries guide chunks; uncovered declarations and module code remain searchable. Large ranges split at complete lines, with source excerpts capped at 6,000 UTF-8 bytes. Oversized lines are skipped and counted. Indexes are limited to 2,000 chunks and 2 MB of embedding input. Batches contain up to 16 excerpts. A failed rebuild preserves the previous complete index. Indexing starts no new batch after 90 seconds; the last in-flight request may take longer. Refresh status before retrying after a client timeout.

There is one AI operation per API process; run one worker. Each question is independent, and the UI retains only the last 10 answers in memory. No conversation history is stored or sent. Models can still misinterpret evidence: citation IDs are checked against retrieved excerpts, but those checks do not prove that a claim is true. The model can return insufficient context. Retrieval has no calibrated relevance cutoff yet; both modes can retrieve irrelevant excerpts. Dependency expansion follows static import adjacency, not runtime calls.

### Hybrid retrieval and diagnostics

Hybrid mode is the default; `strategy: "semantic"` retains cosine-only ranking for comparison. Keyword search uses BM25 over excerpt source, path, and symbol, splitting snake_case and camelCase identifiers. Exact symbol and full-path matches receive an additional ranking channel. Weighted reciprocal-rank fusion combines the top 50 results per channel without treating different score scales as comparable probabilities.

Four of the six context slots retain the highest fused results. Up to two slots can add one excerpt per new file adjacent to the top two seed excerpts, following resolved imports in either direction. Expansion stops after one hop; unresolved imports never become edges. Empty expansion slots are filled from ranked results. Graph size limits skip expansion with a visible note. Existing semantic indexes can be reused; this milestone needs no migration or embedding rebuild.

Expand **Retrieved context** below an answer or preview to see source locations, cosine similarity, keyword score, exact-match presence, fusion score, and dependency provenance. These describe selection, not answer confidence. Preview results are labeled with the submitted question and mode; a later Ask request runs retrieval again rather than trusting a stale preview.

### Retrieval evaluation

Twelve curated questions cover known symbols and multi-file flows in [evaluation/questions.json](apps/api/evaluation/questions.json). They are a small regression fixture, not a held-out production benchmark.

```sh
# Real lexical search with and without graph expansion; no key or network needed.
apps/api/.venv/bin/python -m codeatlas.retrieval.evaluate --offline

# With a configured key: reuse the same embeddings across three retrieval modes.
apps/api/.venv/bin/python -m codeatlas.retrieval.evaluate --live
```

The live comparison reports semantic-only, hybrid without expansion, and hybrid with expansion. Both commands report Recall@1/3/6, MRR@1/3/6, per-question rankings, and elapsed time. Neither generates answers. Offline evaluation has no synthetic semantic vectors and cannot establish semantic/hybrid quality.

[Recorded offline results](docs/evaluation-m4-offline.json): lexical Recall@6 **0.9167**, MRR@6 **0.8125**; graph expansion left these aggregate results unchanged. No live semantic comparison or answer-faithfulness score is claimed because this environment has no configured key. Negative-question calibration and larger held-out evaluations remain work to do before making quality claims. See [verification notes](docs/verification.md).

The adapter follows the official [embeddings guide](https://developers.openai.com/api/docs/guides/embeddings) and [structured output guide](https://developers.openai.com/api/docs/guides/structured-outputs). Responses use `store: false`; source text and questions are treated as untrusted data, and no execution tools are available to the model.

## Checks

```sh
apps/api/.venv/bin/pytest apps/api/tests -q
apps/api/.venv/bin/ruff check apps/api
apps/api/.venv/bin/ruff format --check apps/api
npm run lint
npm run typecheck
npm test
npm run build
docker compose config --quiet
apps/api/.venv/bin/alembic -c apps/api/alembic.ini check
curl -i http://127.0.0.1:8000/api/ready
```

Backend tests use generated hostile archives, small fixture repositories, mocked GitHub responses, the real parser subprocess, and an ephemeral SQLite database with foreign keys enabled and actual Alembic migrations. Live PostgreSQL/GitHub verification is recorded separately. Tests never require downloading a massive real repository.

## Roadmap

0. **Foundation — complete:** monorepo, service shells, configuration and health.
1. **Deterministic analysis — implemented:** safe ingestion, symbols, persistence and explorer.
2. **Dependency graph — implemented:** Python/JS/TS import resolution, graph API, React Flow visualization.
3. **Grounded Q&A — implemented:** semantic indexing, provider boundary, cited answers and an initial evaluation harness. Live model quality remains unmeasured in this environment.
4. **Hybrid retrieval — implemented:** keyword/symbol fusion, bounded graph expansion, diagnostics and comparison harness. Live quality measurement remains pending.
5. **Read-only agent — next:** constrained tools and structured traces.
6. **Reviewable edits:** isolated workspaces and diffs.
7. **Sandboxed tests:** bounded execution and retries.
8. **Approved pull requests:** explicit human approval before remote changes.
