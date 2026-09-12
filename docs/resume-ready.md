# CodeAtlas: resume and interview package

## Project entry

**CodeAtlas — Agentic Code Intelligence**  
Python · FastAPI · Next.js/TypeScript · Claude · MCP · RAG · PostgreSQL · Docker · GitHub Actions  
Repository: https://github.com/Kumaryan12/CodeAtlas

Copy-ready bullets:

- Built a Claude-powered code intelligence application with bounded tool-use workflows, MCP repository reads, isolated code drafts, reviewed diffs, and explicitly authorized Docker tests.
- Implemented local embeddings and hybrid retrieval over commit-pinned source snapshots; measured **98.1% Recall@6 on 18 labelled questions in a 24-case synthetic benchmark**, comparing four retrieval strategies.
- Added deterministic dependency maps and evidence-backed Python data-flow views, along with agent traces, token/latency measurements, guardrail tests, and CI checks for application and sandbox behavior.

If space is limited, use the first two bullets. Keep the synthetic-benchmark qualifier. Do not describe retrieval recall as model accuracy or add financial-services deployment experience: the evaluation fixtures are synthetic, and CodeAtlas is a code intelligence project.

## Thirty-second explanation

“CodeAtlas helps developers understand a repository and prepare controlled code changes. It parses source deterministically, builds dependency and supported Python data-flow views, and uses local embeddings plus hybrid retrieval to supply evidence to Claude. Its agent chooses tools inside a bounded runtime; edits stay in an isolated draft, and approved tests run in restricted Docker containers. I evaluated retrieval and agent behavior, including failures, and used those results to improve the system.”

Use wording you personally understand and can demonstrate. AI coding assistance was part of development; be transparent about it and be ready to explain, modify and test the code yourself.

## Technical decisions to explain

| Decision | Rationale and tradeoff |
|---|---|
| AST/Tree-sitter for structure | Repeatable source evidence without executing repository code; does not establish runtime behavior |
| Local MiniLM embeddings + Claude | Retrieval avoids a second API key; local CPU latency and generic-English embedding quality are tradeoffs |
| Hybrid retrieval | Combines semantic and exact lexical/symbol signals; graph expansion helped less than expected on the measured corpus |
| MCP read boundary | Typed, repository-scoped tools; MCP itself is not the agent's reasoning or permission system |
| Structured agent decisions | Application validates and executes one allowed action at a time; provider output still needs validation |
| Draft overlay | Changes can be inspected and tested without changing original snapshots or pushing to a repository |
| Docker profiles | Fixed commands and resource/network restrictions; no arbitrary dependency installation |
| Separate finish summary and cited claims | Draft/test results have diff/test evidence; original-source claims have source citations. These evidence types must not be confused |

## What to demonstrate

Use the [five-minute demo](demo.md). Show the [readiness evidence](resume-readiness-evidence.md), [earlier audit](project-audit.md), and saved failures as well as successes. The repair workflow has a runnable CLI and recorded traces; the records must be labelled as recorded runs when shown.

## Claims to avoid

- “Production-ready autonomous software engineer.”
- “98.1% answer accuracy” or “100% reliable agent.”
- “Complete data lineage for any language.”
- “Bank-compliant” or “deployed in financial services.”
- “Hallucination-free” or “all malicious inputs are blocked.”

CodeAtlas is a strong personal engineering project with bounded capabilities and measured limitations. Authentication, durable jobs, broad independent evaluation and production operations remain outside the verified scope.
