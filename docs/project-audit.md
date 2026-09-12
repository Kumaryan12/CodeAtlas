# CodeAtlas project audit and interview guide

Audit measurements: 12 September 2026 (UTC); report finalized 13 September 2026. Core implementation checked at `21d6fec`; this report and the repair-demo harness are added afterward. Machine-readable evidence: [audit metrics](project-audit-metrics.json).

**Assessment:** CodeAtlas is a substantial portfolio MVP with verified deterministic analysis, RAG, bounded agent execution, MCP integration and sandbox boundaries. It is resume-ready as a personal project. It is not production-proven, and live-agent completion and citation quality remain material gaps. Passing software tests does not imply that all model answers are correct.

## Fresh verification

| Check | Result | What it establishes |
|---|---:|---|
| Backend suite, all opt-ins enabled | **240 passed; 0 skipped; 0 failed** | Includes real local embeddings and seven real Docker checks; approximately 54 seconds on this machine |
| Frontend tests | **23 passed** | Graph filtering/layout, scoped proxy rules, source rendering, citations and run-state helpers |
| Python lint and formatting | Pass | Ruff checks |
| Frontend lint and type checking | Pass | ESLint and TypeScript checks |
| Frontend production build | Pass | Next.js compilation and build generation |
| PostgreSQL schema check | Pass | Current database agrees with migration metadata |
| Scripted agent through MCP | **6/6 pass** | Two task cases and four guardrail cases; scripted decisions, not model quality |
| Stored repository graph checks | **14/14 HTTP 200** | Dependency and Data Flow endpoints for seven snapshots across four distinct repositories; all edges reference files in their own snapshot |
| GitHub Actions after fix | **3/3 jobs passed** | Backend/migrations, frontend, real Docker boundaries on hosted Linux |
| Visual browser interaction | **Not verified** | No browser session was available; HTTP/build checks are not visual QA |

The 240 backend and 23 frontend tests are separate suites. Do not add the six scripted evaluation cases or repair-demo assertions to these counts as if they were additional unit tests.

Hosted CI evidence: [passing run for 21d6fec](https://github.com/Kumaryan12/CodeAtlas/actions/runs/34709965115). CI intentionally skips the optional local model download, while this local audit enabled it. The local test warning is a dependency's deprecated AnyIO alias; it did not fail the suite.

## What we built

| Area | Implemented behavior |
|---|---|
| Repository ingestion | Public GitHub default-branch import pinned to a commit; bounded archive processing; stored immutable source snapshots |
| Deterministic analysis | Python AST and JS/TS Tree-sitter symbol/import extraction without executing repository source |
| Dependency architecture | Local import resolution, source evidence, unresolved reasons, cycle detection, filters, neighborhood focus and interactive graph layout |
| Data Flow architecture | Separate producer-to-consumer view for supported Python function-return/argument patterns, with call-site evidence and explicit coverage limits |
| Architecture usability | Arrow labels distinguish imports from value passing; unconnected files hidden by default with a show/hide control |
| Retrieval | Symbol-aware chunks, pinned local CPU embeddings, semantic search, lexical/exact-symbol signals, hybrid ranking and optional graph expansion |
| Answers | Claude generation over retrieved excerpts, structured claims/citations, reference validation and insufficient-context responses |
| Agent runtime | Bounded decision → tool → observation loop; recorded plans, read/write/execute steps, errors and available provider usage |
| MCP | Scoped repository read tools through a controlled MCP server/client boundary; local handlers for other supported tools |
| Controlled editing | Isolated draft overlay, read-before-edit/version checks, diff review and downloadable patch; original source remains unchanged |
| Testing sandbox | Explicit test-profile permission, fixed trusted Docker images, network isolation, read-only source mount, non-root execution and resource/output/time limits |
| Evaluations and delivery | Scripted runtime checks, live Claude/MCP evidence, RAG ablations, adversarial/unsupported cases, CI and reproducible reports |

This is a single bounded tool-using agent architecture. Multi-agent orchestration, durable background queues, general-purpose long-term memory, authentication, private-repository ingestion and production deployment governance are not established by this project.

## What improved, with evidence

| Before | After | Evidence / qualification |
|---|---|---|
| Embeddings required a second provider key | Local CPU MiniLM embeddings; Claude still generates answers | Real 384-dimensional embeddings exercised; fixed model revision and pooling/chunk fingerprint |
| Long source could exceed MiniLM's normal token window | Token windows include source tails and normalized window aggregation | Actual-model long-tail regression passes; aggregation can still dilute detail |
| Original 12-question retrieval fixture | Additional **24-case** synthetic RAG corpus with 18 positive relevance cases and six unsupported cases | Four retrieval strategies and separate answer/abstention/citation checks; not independently held out |
| F1 root-package imports were rejected | Six local import connections resolved | Unresolved observations dropped **43 → 33**; remaining entries are external/unclassified, not all broken dependencies |
| One architecture map blurred import direction and data movement | Dependency and Data Flow views with distinct arrow meanings | F1 includes `data.py → features.py → model.py` in supported static value flow |
| Unconnected nodes cluttered the canvas | Hidden by default with an explicit show/hide count | Incoming-only nodes remain visible; self-loops alone do not count as connections to other files |
| Claude thinking blocks could invalidate parsing | Text blocks extracted while supported thinking blocks are excluded from stored answers | Existing provider regression tests; no hidden reasoning stored |
| Live RAG's ten-second read timeout caused frequent failures | Thirty-second read timeout matching the existing response limit | Previous separate retry recovered 13/19 failures; five timeouts and one schema rejection remained |
| Sandbox output-flood cleanup failed in hosted CI | Attached output reader terminated/closed before forced container removal | stdout/stderr flooding checks pass locally; hosted CI changed from failure to **3/3 passing jobs** |

The Docker fix was found during this audit. [The failing run](https://github.com/Kumaryan12/CodeAtlas/actions/runs/34708992707) showed `sandbox_cleanup_failed` for excessive output. The code previously attempted removal while its attach pipes could remain blocked. Detaching the reader first fixed the tested failure without removing the output limit or relaxing the test.

## Retrieval metrics: freshly reproduced

Same frozen 40-chunk, eight-file synthetic corpus; macro averages across **18 positively labelled questions**. The six unsupported questions are excluded from ranking metrics.

| Retrieval strategy | Recall@6 | MRR@6 | nDCG@6 | All labelled evidence@6 |
|---|---:|---:|---:|---:|
| Lexical | 96.8% | 0.944 | 0.924 | 16/18 |
| Semantic | 95.4% | 0.944 | 0.920 | 15/18 |
| Hybrid | **98.1%** | **1.000** | **0.975** | **17/18** |
| Hybrid + graph | 95.4% | 1.000 | 0.958 | 15/18 |

Hybrid improves Recall@6 over semantic-only by **2.8 percentage points** in this run. Graph expansion reduces coverage relative to plain hybrid on this corpus: nearby-file excerpts sometimes displace useful ranked evidence. We retained that result rather than tuning the benchmark or switching the production default after seeing it.

Recall measures labelled evidence recovered; MRR measures the rank of the first relevant result; nDCG rewards relevant results near the top. **98.1% retrieval recall is not 98.1% answer accuracy.** Perfect MRR on 18 curated questions does not imply complete evidence or general performance. Corpus and question hashes, model fingerprint and per-category metrics are in the JSON report.

## Live model results: previous RAG run versus fresh repair demo

### Previous RAG answers — not rerun in this audit

- Initial run: **5/24 accepted responses**, 19 timeouts.
- Retry of only those failures: **13/19 accepted responses**, five timeouts, one schema rejection.
- Latest result per question: **18/24 accepted**, after **43 total attempts**. This is a recovery summary, not a 75% first-pass success rate.
- Unsupported questions: **6/6 correctly abstained** across their latest attempts.
- Known recorded usage across both runs: **28,063 input / 3,406 output tokens**. Timeout billing can be unreported; these are incomplete billing totals and no dollar cost is asserted.
- Valid reference IDs did not guarantee complete or well-supported claims. The [qualitative source review](rag-results-review.md) documents an incomplete cross-file explanation, a claim supported only by caller/import excerpts, and unnecessary injection-marker quotation.

Earlier live read-only Claude/MCP evaluation: **4/6 automatic passes**. Both flagged runs quoted a strict attack marker while rejecting its instruction; these remain flags requiring contextual review, not silently converted to passes. See [the original report](evaluation-agent-live.md).

### Fresh Claude repair demo — mixed outcome

The [full repair trace](evaluation-repair-live.json) is a new real-model test of a small authored bug: `normalize_email()` stripped whitespace but failed to lowercase addresses. Original tests ran only inside Docker.

| Stage | Observed result |
|---|---|
| Original implementation | Two tests ran; normalization failed |
| Claude draft | Changed only `auth.py`: `email.strip()` → `email.strip().lower()` |
| Diff review | Agent called `view_diff` |
| Agent's authorized test run | Passed against the final draft digest |
| Independent verification | Original, unmodified tests rerun against the patch: **2/2 passed** |
| Source preservation | Original repository files unchanged; no upstream patch applied |
| Final model response | **Rejected: `invalid_agent_decision`** |
| Overall run | **Failed**, despite the successful tested patch |

The run used **eight model calls**, took **45.1 seconds**, and recorded **29,563 input / 2,698 output tokens**. Cost is unknown because pricing was not configured. Seven tool steps completed before the final decision failed. The trace distinguishes MCP reads from local draft/testing operations.

This verifies that a live model can create a correct draft and exercise the sandbox workflow on this fixture. It does **not** establish reliable end-to-end completion or real-repository bug-fix accuracy. The final schema rejection remains an open issue; its precise cause is not established by the sanitized trace.

## Remaining work and priorities

1. **Final agent response reliability:** investigate schema failures without exposing raw secrets or relaxing validation. Preserve the current failure as a regression/evaluation case.
2. **Provider reliability:** measure timeout behavior under repeatable conditions before choosing bounded retry/backoff or changing model settings. Current historical RAG failures remain unresolved.
3. **Claim-level evidence:** separate citation-ID validity, factual correctness, completeness, and entailment. Caller-only evidence should not be treated as proof of callee behavior.
4. **Broader evaluation:** create an independently reviewed question/bug set over real repositories. Current graph checks cover real snapshots, but RAG and repair quality benchmarks remain synthetic.
5. **Visual user testing:** exercise both architecture views, filters, source links, Ask and Agent tabs in a real browser. Automated browser access was unavailable.
6. **Production maturity, if pursued later:** authentication, durable jobs, multi-user isolation, deployment monitoring and operational recovery. No production-readiness claim is justified today.

There is no need to add another AI framework before understanding and improving these behaviors.

## Reproduce the checks

Run from the repository root, with the existing virtualenv, prepared local embedding weights, running Docker, and trusted sandbox images:

```sh
CODEATLAS_TEST_DOCKER=1 CODEATLAS_TEST_LOCAL_EMBEDDINGS=1 \
  apps/api/.venv/bin/pytest apps/api/tests -q
apps/api/.venv/bin/ruff check apps/api
apps/api/.venv/bin/ruff format --check apps/api
npm run lint
npm run typecheck
npm test
npm run build
apps/api/.venv/bin/alembic -c apps/api/alembic.ini check
apps/api/.venv/bin/python -m codeatlas.evaluation.rag --output /tmp/rag-local.json
apps/api/.venv/bin/python -m codeatlas.evaluation.agent --scripted --transport mcp
```

The following command explicitly makes live provider calls and runs the synthetic fixture inside Docker. It writes an artifact and exits nonzero when the overall repair checks fail:

```sh
apps/api/.venv/bin/python -m codeatlas.evaluation.repair --live --output /tmp/repair-live.json
```

Build and development commands both generate Next.js output; restart the local development server if needed after a production build. Existing `.env` credentials must be preserved and must not be copied into reports.

## Demo and interview preparation

A practical ten-minute walkthrough:

1. Explain the immutable snapshot and parser boundary, then open an existing repository.
2. In Architecture, contrast **Dependencies** with **Data Flow**, and toggle unconnected files. Use F1's flow and its `main.py` evidence to explain the distinction.
3. In Ask, inspect retrieved excerpts before requesting an answer. Explain where local embeddings end and Claude begins; inspect every cited claim.
4. Show the saved repair diff, successful Docker test output and preserved source. Also show the failed final decision instead of presenting the run as fully successful.
5. Show the four retrieval strategies, graph-expansion regression and green hosted CI. Explain why ranking metrics and test counts are not model accuracy or proof of safety.

Resume wording you can defend:

> Built CodeAtlas, a Python/FastAPI and Next.js code intelligence application with Claude tool-use workflows, MCP repository tools, local embeddings, hybrid RAG, evidence-backed architecture views, isolated drafts and Docker sandbox testing.
>
> Implemented 263 passing backend/frontend tests and reproducible agent/RAG evaluations; measured 98.1% Recall@6 for hybrid retrieval on 18 labelled questions within a 24-case synthetic benchmark, and resolved a Linux CI sandbox-cleanup failure.

The test-count statement is tied to this audit. For interviews, lead with the engineering problem and tradeoffs rather than just the numbers. Be ready to explain a request through the code, identify where it can fail, and show the corresponding evidence.
