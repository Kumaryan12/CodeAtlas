# Development guide

## Source analysis architecture

The browser uses Next.js's fixed same-origin repository proxy. FastAPI validates the request, creates an `importing` snapshot, resolves the public repository's default branch to a commit, and downloads a bounded archive. A trusted Python subprocess decompresses/scans the archive and invokes Python AST or Tree-sitter. It returns normalized files and symbols as JSON. The parent process stores those results with bulk inserts in a database transaction and marks the snapshot `ready` or `partial`.

A handled download/analysis failure marks the snapshot `failed` without publishing partial file rows. A transient database write failure rolls back all results and attempts to record failure in a fresh transaction. If the database remains unavailable, that status cannot be saved; the stale snapshot is an explicit limitation.

The subprocess never starts a repository interpreter, runs its entry point, imports its modules, installs dependencies, or invokes its tests. `python -I -m codeatlas.ingestion.worker` loads the installed trusted CodeAtlas package, not code from the downloaded repository. Its environment does not receive database credentials.

## Decisions and interview questions

| Choice | Why | Alternatives / trade-offs | Interview question |
| --- | --- | --- | --- |
| Commit-pinned archives | Repeatable source locations with a recorded SHA; no Git hooks or history download | Shallow clone supports more Git operations but adds process/Git configuration boundaries | What happens if a branch changes during indexing? |
| Fixed GitHub hosts, no redirects | User input cannot select an arbitrary network destination | Following verified redirects could support renamed repositories but increases validation complexity | How do you prevent SSRF in repository ingestion? |
| Bounded decompression before tar interpretation | Extended headers and compression ratios also consume resources | Streaming tar directly saves disk but makes expansion/header limits easier to miss | Why is checking compressed download size insufficient? |
| Python AST plus Tree-sitter | Python's built-in grammar gives reliable structure; Tree-sitter covers JS/TS/JSX/TSX and partial syntax errors | Regex cannot reliably model nested syntax; one parser framework would simplify interfaces but add Python grammar dependencies | Why not extract functions with regex? |
| Normalized parser results | Parser-specific trees stay inside parser modules; downstream storage/UI share one symbol shape | Persisting raw ASTs exposes consumers to language-specific schemas | How would you add another language? |
| Separate trusted parser process | Hard timeout can terminate stuck Python or native parser work | Thread timeouts cannot reliably stop native work; containers add a stronger boundary but more infrastructure | What does process isolation protect, and what does it not protect? |
| Three relational tables | Snapshots own files; files own symbols; FKs enforce ownership and parent relationships | Graph/vector stores are premature before graph/retrieval requirements exist | What consistency should a completed snapshot guarantee? |
| Source stored once | Symbol line ranges provide source access without duplicating nested bodies | Storing snippets is convenient for retrieval but needs synchronization/versioning | How do citations remain valid after the repository changes? |
| Bulk writes inside one transaction | Avoid per-symbol/file round trips; either all analysis results are committed or none are | Per-file commits reduce transaction size but make completed-state semantics harder | How do you avoid partially indexed snapshots? |
| Synchronous one-import gate | Small MVP with visible error handling and no queue infrastructure | A durable queue supports retries/progress and multiple workers; needed before wider deployment | What breaks if you run multiple API workers today? |
| Same-origin proxy | Backend address remains server-side; fixed route allowlist and browser-origin checks | Direct browser API calls avoid a hop but require CORS/deployment decisions | Why compare Origin to the actual Host header rather than Next.js's normalized URL host? |
| Paginated source and bounded highlighting | Prevent very large files/symbol lists from overwhelming rendering | Virtualized editors provide smoother large-file navigation with more dependencies | How do you keep a source viewer responsive on untrusted input? |

The existing monorepo and application factory keep frontend/backend runtimes separate and resource lifecycle explicit. Synchronous database work runs in FastAPI's thread pool; only the parsing subprocess is force-terminated on its deadline. No total wall-clock limit covers database transaction time or process startup, so this is not yet a production job scheduler.

Reference documentation: [Tree-sitter Python binding](https://tree-sitter.github.io/py-tree-sitter/), [Alembic migration environment](https://alembic.sqlalchemy.org/en/latest/tutorial.html), [GitHub repository contents/archive API](https://docs.github.com/en/rest/repos/contents).

## Database and migration workflow

- `repositories`: immutable source identity plus analysis state, counts, languages, skip counts and safe failure text.
- `repository_files`: repository-scoped unique paths, language, source, size, parser warning and observed imports.
- `code_symbols`: file ownership, type, name, parameters, parent symbol and line ranges. Repository and language can be obtained through the owning file.
- No users, conversations, agents, embeddings or graph tables yet.

Run migrations explicitly with `apps/api/.venv/bin/alembic -c apps/api/alembic.ini upgrade head`. Startup never invokes `create_all`. Run `alembic ... check` against PostgreSQL after model changes. Tests apply, compare, downgrade and reapply the exact migration on ephemeral SQLite with foreign keys enabled; this is complemented by live PostgreSQL validation, not a replacement for it.

The migration creates foreign keys, a repository/path uniqueness constraint, a symbol/file index and a snapshot-created-time index. Path/file pagination and snapshot-scoped lookup avoid exposing filesystem access. File and symbol summary queries deliberately exclude source text; deferred-column guards prevent an accidental lazy reload that would duplicate large source bodies across symbols. Reimporting creates a distinct identity and does not overwrite old source.

## Working conventions

- Implement one reviewable milestone at a time; inspect current state first, preserve working behavior and stop at the agreed milestone boundary.
- Commit and push to `Kumaryan12/CodeAtlas` at meaningful checkpoints after inspecting staged content.
- Never commit `.env`, generated dependencies/builds, or imported repository workspaces.
- Keep parser fixture files out of automated formatting: exact source locations and malformed examples are intentional test inputs.
- Add only layers used by current behavior. API endpoints share database/session dependencies; ingestion orchestration and parsers stay outside route handlers.
- Do not execute untrusted source. Future test execution needs an actual sandbox, permissions, resource controls and traces.
- Keep future model providers behind interfaces; introduce those interfaces when Q&A begins.

The [source tree](structure.md) lists the actual tracked files.

## Intentional debt and next work

The local application has no authentication, total storage quota, deletion/retention policy, durable queue, crash recovery, cross-process import lock, CI, retrieval, LLM or agent. Imports have bounded network streams and a hard analysis timeout, but the parser process is not an OS sandbox. Native-parser exploitation and memory isolation need stronger boundaries before accepting arbitrary repositories in a hosted multi-user deployment.

Archive scanning is intentionally conservative: reject links and unusual paths, skip generated files using heuristics, and show only supported UTF-8 source files. `.gitignore` semantics, encodings other than UTF-8, CommonJS imports, anonymous exports and overload semantics remain future parser refinements. Tree-sitter can report diagnostics for valid framework syntax; a real self-import exposed its bare-ampersand JSX-text limitation, which remains visible as a partial-index warning rather than being suppressed.

ESLint 9 is retained because the current Next.js React lint plugin failed with ESLint 10; its upstream support warning is known tooling debt. Backend tests still expose upstream Starlette/httpx and AnyIO deprecation warnings. The frontend retains Webpack because Turbopack's CSS worker could not bind its internal port in the original managed environment.

## Milestone 2: derived dependency graphs

Migration `0002` adds nullable `repository_files.import_references` and `repositories.resolution_configs` JSON columns. NULL means legacy coverage; new empty lists mean capture ran but found no imports/configuration. Source and existing symbol identities are preserved. No graph tables were added: graphs can be recomputed from immutable, bounded metadata using the current resolver.

The isolated parser now captures import kind, module specifier, imported Python names and statement line. The archive scanner separately reads bounded strict-JSON tsconfig/jsconfig files, storing only supported alias options and diagnostics. Configuration is data: no plugins run, and `extends`/project references are never fetched.

`GET /api/repositories/{id}/graph` selects metadata only, resolves local files, groups duplicate source/target pairs with their import evidence, reports unresolved/ambiguous observations and computes strongly connected components. It rejects unfinished snapshots. It does not reparse untrusted source during a request, access the network or use user paths for disk access.

| Choice | Why | Alternative / trade-off | Interview question |
| --- | --- | --- | --- |
| On-demand graph from stored metadata | Avoid duplicated graph state and another migration/table lifecycle | Persisted versioned graphs/caching may help larger workloads; current requests recompute | What makes a graph cache invalid? |
| Structured import references plus legacy fallback | Preserve imported names and exact evidence without breaking old snapshots | Reparse all old source would require a bounded migration job, not an HTTP read | How do you evolve an analysis schema safely? |
| Explicit ambiguity and unresolved imports | Avoid inventing edges when aliases, packages or runtime paths are unknown | Compiler/language-server integration is more precise but substantially heavier | How do you express uncertainty in static analysis? |
| Scoped Python root inference | Support src layouts, monorepos and namespace packages without executing setup code | Installed environment metadata is more authoritative; inferred edges are dashed and labelled | Why can static imports differ from runtime imports? |
| Narrow configuration subset | Useful TS aliases with bounded data parsing and no code execution | JSONC/inheritance/package exports need further specification and fixtures | Which compiler options materially change resolution? |
| Iterative strongly connected components | Linear graph traversal without Python recursion-depth failures | Enumerating every cycle can be exponential and is unnecessary for cycle highlighting | Why are SCCs useful in dependency analysis? |
| Bounded React Flow view | Pan/zoom, inspection, filtering and a 200-file rendering cap | Full unbounded rendering can overwhelm the browser; API results remain available | How do you keep a graph visualization responsive? |

The resolver returns local indexed file edges only. JS/TS extension and index candidates are deliberately conservative if several exist. Python roots inferred from file suffixes must contain the importing file before a unique match is selected; multiple out-of-scope candidates remain ambiguous instead of choosing an unrelated application. Namespace inference does not treat every file's directory as a search root: doing that creates false self-imports for a nested `logging.py` importing standard-library `logging`. Qualified namespace modules are supported; unconfigured bare imports from arbitrary script/test directories may remain unresolved. This is a source graph, not proof of module loader behavior. Static type-only import declarations are included; CommonJS and dynamic imports are not extracted yet.

Graph results may change when resolver logic improves even though snapshot source is immutable. Add resolver versioning/cache keys if graphs become persisted evaluation artifacts. No LLM, call graph or sandbox execution was introduced.

## Proposed Milestone 3

Add grounded repository Q&A with code-symbol retrieval, a swappable embedding/LLM provider boundary, and source citations. Start with a small retrieval evaluation fixture and known supporting symbols; introduce embedding persistence and migrations only as needed. Keep model configuration in environment variables, and expose missing-configuration errors. Do not send whole repositories to a model or add write/execution tools.

Milestone 3 begins only after the user's next instruction.
