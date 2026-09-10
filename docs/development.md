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

## Milestone 3: grounded Q&A

Migration `0003` introduces `semantic_indexes` (one complete index per snapshot) and `embedding_chunks` (source range, symbol metadata, excerpt, and JSON vector). Source snapshots and parser symbols remain the system of record. An index fingerprint includes provider, embedding model, and chunker version. Foreign keys scope chunks to their snapshot and file and cascade on deletion.

| Choice | Reason and tradeoff | Interview question |
| --- | --- | --- |
| Symbol-first disjoint excerpts | Innermost functions/methods retain their bodies; enclosing declarations and remaining module lines stay searchable without duplicating entire classes. Very large symbols split at line boundaries. | Why are fixed character chunks poor for code? |
| JSON vectors + exact cosine search in PostgreSQL | Reuses existing infrastructure and works with SQLite tests. O(chunks × dimensions) search is acceptable only for the explicit 2,000-chunk cap; use pgvector and indexed similarity search when scale justifies it. | When would you introduce a vector index? |
| Atomic index replacement | Network calls finish before replacing persisted vectors. Failure preserves the old complete index; retrying may repeat billable embedding calls because partial batches are not cached. | How do you avoid exposing partially indexed data? |
| Provider Protocol + one OpenAI adapter | `embed` and `answer` are injected into services; HTTP wire formats are confined to `ai/provider.py`. Adding a vendor also requires extending configuration and the index fingerprint/status wiring. No SDK dependency was necessary because httpx was already installed. | Which parts of a provider swap invalidate stored vectors? |
| Structured claims with excerpt IDs | Server-owned file IDs and line ranges prevent model-invented clickable references. They cannot establish semantic entailment or fully eliminate prompt injection. | Why does valid JSON not guarantee a grounded answer? |
| Independent questions and transient UI turns | Avoids prematurely adding conversation/message tables or mixing stale prior answers into retrieval. Follow-up pronouns are not resolved; persistent multi-turn state is deferred. | How would conversation history change retrieval? |

The model receives at most six excerpts, with no tools, and cannot write or execute code. Prompts explicitly mark repository text and questions as untrusted. Provider response bodies are bounded to 2 MB, with 5-second connection/10-second I/O timeouts and a 30-second checked response deadline (an in-flight read can extend it). HTTP errors are sanitized. Application logs record event, snapshot, status, and duration, not prompts, source, or API keys. The model's output is rendered as text, not HTML or executable Markdown.

A process lock bounds AI concurrency. This is intentionally a local single-worker application; a production deployment needs authentication, distributed job coordination, cancellation, quotas, and durable progress. Indexing currently returns once complete; it does not claim percentage progress. Parser warnings and oversized-line omissions remain visible. Module-level source is indexed, but non-source configuration and documentation are not yet included.

Evaluation fixture questions test known supporting symbols. The opt-in CLI computes real-provider Recall@1/3 and MRR@1/3; offline tests verify mechanics with synthetic vectors. The current environment has no configured key, so semantic quality and answer faithfulness are unmeasured. Further evaluation should add negative questions, larger held-out repositories, human evidence review, and model/token usage accounting.

## Milestone 4: hybrid retrieval

No database migration or provider change was needed. The stored chunk/vector schema supplies the new retrieval signals. `retrieval/hybrid.py` is a pure ranking function shared by the Q&A service and evaluator; `services/dependency_graph.py` loads the same graph used by the architecture endpoint. Both `/ask` and `/retrieve` use the same context-selection function. The default strategy is hybrid, with a semantic-only baseline available in the UI/API.

| Choice | Reason and tradeoff | Interview question |
| --- | --- | --- |
| BM25 + exact symbols/paths | Complements embeddings for identifiers and concrete code vocabulary. Tokenization preserves full identifiers plus snake/camel parts and uses a small English stop-word list; it is not multilingual query understanding. | Why do embeddings miss exact code identifiers? |
| Weighted reciprocal-rank fusion | Combines rankings without adding incompatible raw score scales. Formula: sum of channel weight / (60 + one-based rank), over top 50 per channel. Semantic and BM25 weights are 1; the explicit-match channel weight is 2. These are initial heuristics, not tuned confidence estimates. | Why use rank fusion instead of summing cosine and BM25? |
| Explicit-match channel | Whole symbol match scores 2 and whole path match scores 1 before channel ranking; no substring symbol match. Matching is case-insensitive and bounded to stored symbol labels. Duplicate symbols still require path/context disambiguation. | How do you distinguish two functions with the same name? |
| Four ranked seeds + two expansion slots | Preserves core retrieval while adding at most two new adjacent files from the top two seed excerpts. One excerpt per new file, one hop, no recursion. Neighbors outside the channel top 50 can still be selected. Import adjacency can introduce irrelevant context. | How do you prevent graph expansion from overwhelming the prompt? |
| Preview endpoint | One embedding call, no answer-model call. Scores, selection reason, via-file provenance, and exact source ranges are visible before asking. Preview does not cache or authorize a later answer call; Ask retrieves afresh. | How do you debug a wrong RAG answer? |
| Recompute bounded lexical scores | Uses the existing 2 MB / 2,000-chunk index cap without new search infrastructure. For larger repositories, move term statistics/postings to persistent indexes and add pgvector as justified by measured latency. | When should an in-memory prototype become an indexed search service? |

Graph lookup loads metadata without source. Only resolved edges within the selected snapshot participate. Legacy and unsupported-resolution notes remain visible; oversized graphs skip expansion and explicitly report it. Scores are included in diagnostics but not sent to the answer model, so numeric ranking values do not masquerade as evidence.

The evaluation fixture now contains 12 questions, 14 chunks, and two resolved file-import edges. `--offline` exercises actual lexical retrieval without provider calls; `--live` embeds fixture chunks and questions once and compares semantic, hybrid, and hybrid-plus-graph under the same six-excerpt budget. Metrics are calculated on expected file/symbol labels and include per-question rankings. The recorded offline experiment yielded Recall@6 0.9167 and MRR@6 0.8125, unchanged by graph expansion. This small curated set does not demonstrate generalization. Synthetic-vector tests separately verify exact-match recovery against misleading semantic rankings and bounded expansion under cycles/high candidate counts.

There is no calibrated relevance threshold or evidence-entailment check. Live semantic/answer-quality evaluation is still unavailable without a configured key. Do not infer improved answer quality from successful unit tests or valid citation IDs.

## Milestone 5: read-only investigations

Migration `0004` adds one `agent_runs` table: snapshot ID, submitted task, model, lifecycle state, timestamps, a public plan, bounded trace steps, final claims/reference metadata, and sanitized errors. An index supports snapshot history ordered by creation time. The trace is a small JSON list (at most 11 model/read entries), so a separate step table is unnecessary at this stage. Each step is committed before and after the operation so polling sees real progress.

| Choice | Reason and tradeoff | Interview question |
| --- | --- | --- |
| Application-dispatched structured decisions | The model chooses an action after each observation. A provider interface returns a validated decision, and the application owns dispatch; no hosted execution tools are enabled. This avoids a framework dependency while keeping the control loop explicit. | What makes this an agent rather than one-shot RAG? |
| Fixed read registry and scoped parameters | Only list files, find symbols, hybrid search, bounded file reads, and dependency inspection exist. File access uses UUIDs scoped to the snapshot, never filesystem paths. | Why is a read-only prompt insufficient as a security boundary? |
| Evidence IDs assigned by the server | Reads/search register exact source ranges as E1, E2, etc. Final implementation claims must cite inspected IDs; file/symbol/dependency metadata alone is not evidence. Semantic entailment still requires evaluation. | How do you reject a plausible-looking invented citation? |
| Incremental trace persistence | Commits record actual model/read starts, completions, failures, and durations. Public plans and concise action summaries are shown; internal reasoning and raw tool-output bodies are not stored. | How do you diagnose a failed run without logging source and secrets? |
| One bounded background run | HTTP 202 separates creation from completion; the UI polls progress. The existing AI lock is held until the worker exits. There is no durable queue, cross-process coordination, resumability, or cancellation. | What changes when this becomes a multi-worker service? |
| Explicit budgets and failure states | Six decisions, five tool attempts, 12 evidence excerpts / 24 KB source, and 48 KB serialized context bound growth. Time is checked before decisions and reads; in-flight calls may finish after 90 seconds. | How do you contain looping behavior and model cost? |

The OpenAI adapter uses [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) for a decision envelope containing a public plan, action, arguments, and optional final claims. Server Pydantic validation and a static dispatch table remain authoritative. Native hosted shell/tools are not enabled. Other providers can implement `InvestigationProvider.decide` and `embed`; existing Q&A behavior remains independent.

`find_symbol` searches existing parser metadata without embeddings. `search_code` reuses Milestone 4 retrieval but returns at most two evidence excerpts. A missing/stale index becomes a tool error the model can respond to with file/symbol reads. Invalid parameters and repeated calls consume the same attempt budget as successful reads. Invalid model decisions, malformed final results, and invented citations fail the run. Tool faults remain visible observations so the model can choose another allowed read within its budget.

Read tools never write repository tables or execute/import repository source. The controller writes only run metadata. Final run results persist source locations rather than copying source bodies; the API hydrates cited ranges from the immutable snapshot. The user's task is persisted intentionally for run history, and the UI discloses local storage and external model calls. Query arguments and tool-output bodies remain transient. Model summaries can contain user-facing text, so they are rendered as plain text.

Startup recovery marks unfinished runs and pending steps interrupted/failed. It does not rerun them. Missing database/schema availability is tolerated so health endpoints remain usable; recovery requires another API restart if the database was unavailable at startup. Use one worker: startup recovery assumes there is no other live process owning a run. Durable scheduling, distributed coordination, cancellation, and detailed token/cost accounting remain explicit production work.

Scripted-provider tests prove control flow and boundaries, not autonomous investigation quality. Live semantic and agent evaluation still requires a configured key. Before relying on findings, run representative tasks with expected evidence, include misleading-source instructions and negative questions, and assess faithfulness and useful task completion.

## Milestone 6: isolated source drafts

Migration `0005` adds `AgentRun.mode` (default `investigate`, including existing rows) and `changes` (JSON object, default `{}`). The immutable snapshot plus a bounded per-run overlay forms a persistent source workspace. This avoids copying every snapshot file or introducing filesystem privileges before Milestone 7. `DraftWorkspace` has no filesystem, subprocess, or network capability; its only mutations replace the current run's overlay. Nothing writes `RepositoryFile`, parser metadata, embeddings, or GitHub.

The request must explicitly choose `mode: edit`. The server chooses `DraftDecision` and its registry based on the stored mode, never on model output. Read-only runs keep their original schema and registry. The provider uses the corresponding strict structured-output schema. Tools reject extra arguments and unsafe paths. Writes require an exact, uniquely matching text replacement and a current SHA-256 from an actual workspace read, preventing blind or stale edits. Each tool's accepted mutation and completed trace commit together. Errors before commit leave the previous persisted draft intact.

The overlay is bounded to 10 paths, 12 KB UTF-8 per file, 60 KB total. Paths are ASCII source paths up to 200 characters, with no empty/dot/traversal components, backslashes, NUL, or `.git` components. Creation also rejects case and file/directory conflicts with all imported source. Limits are enforced by application code, independent of model instructions. New-file absence is only known relative to the imported subset. No delete/rename, tests, automatic apply, or PR support is claimed.

Editing loops allow 10 tools / 11 model calls and up to 21 trace entries. They share the existing one-operation lock, checked time and context budgets, and restart recovery. A model finish with changes requires `view_diff` for the current overlay. Even on a failed finish, the user can inspect/download partial changes. Diff output is generated with Python's standard library, preserves LF/CRLF and missing terminal newlines, and is tested by applying it with Git in disposable test directories. No product code invokes Git.

`GET .../agent-runs/{run_id}/diff` scopes the run to the requested snapshot and returns a base SHA plus per-file unified diffs. The frontend proxy permits this exact GET path. The UI refreshes the diff as trace/status changes, labels all drafts untested, distinguishes writes, and disables patch download while a run is active or the diff fetch has failed. React renders all model/source text as escaped text. Snapshot citations continue opening original source.

Why a database overlay? Import currently retains only analyzed source, not complete checkouts. A full test sandbox requires a separate future design for retrieving the pinned repository, reconciling the patch, configuring isolation and dependencies, and bounding execution. The present workspace is suitable for reviewing small source proposals, not running a project.

## Next milestone

Milestone 7 is bounded test execution in an actual sandbox, with test output and controlled retries. Live agent quality remains unmeasured; obtain and review a provider baseline before expanding execution authority. Begin only after the user's next instruction.
