# Source tree

Tracked source/configuration/documentation files. Local `.env`, dependencies, build output, database volumes, and temporary workspaces are excluded.

```text
CodeAtlas/
├── .github/workflows/ci.yml
├── apps/
│   ├── api/
│   │   ├── codeatlas/
│   │   │   ├── agents/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── runner.py
│   │   │   │   ├── tools.py
│   │   │   │   └── workspace.py
│   │   │   ├── ai/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── anthropic.py
│   │   │   │   ├── investigator.py
│   │   │   │   └── provider.py
│   │   │   ├── api/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── agent.py
│   │   │   │   ├── health.py
│   │   │   │   ├── qa.py
│   │   │   │   └── repositories.py
│   │   │   ├── core/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── body_limit.py
│   │   │   │   ├── config.py
│   │   │   │   ├── database.py
│   │   │   │   ├── errors.py
│   │   │   │   └── logging.py
│   │   │   ├── dependencies/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── config.py
│   │   │   │   ├── graph.py
│   │   │   │   └── resolver.py
│   │   │   ├── ingestion/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── archive.py
│   │   │   │   ├── github.py
│   │   │   │   ├── runner.py
│   │   │   │   └── worker.py
│   │   │   ├── models/
│   │   │   │   ├── __init__.py
│   │   │   │   └── repository.py
│   │   │   ├── parsers/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── javascript.py
│   │   │   │   ├── python.py
│   │   │   │   └── types.py
│   │   │   ├── retrieval/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── chunks.py
│   │   │   │   ├── evaluate.py
│   │   │   │   ├── hybrid.py
│   │   │   │   └── vectors.py
│   │   │   ├── sandbox/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── docker.py
│   │   │   │   └── service.py
│   │   │   ├── schemas/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── agent.py
│   │   │   │   ├── graph.py
│   │   │   │   ├── qa.py
│   │   │   │   └── repository.py
│   │   │   ├── services/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── dependency_graph.py
│   │   │   │   ├── import_repository.py
│   │   │   │   └── qa.py
│   │   │   ├── __init__.py
│   │   │   └── main.py
│   │   ├── evaluation/
│   │   │   ├── fixture/
│   │   │   │   ├── auth.py
│   │   │   │   ├── catalog.py
│   │   │   │   ├── jobs.py
│   │   │   │   ├── orders.py
│   │   │   │   └── routes.py
│   │   │   └── questions.json
│   │   ├── migrations/
│   │   │   ├── versions/
│   │   │   │   ├── 0001_repository_analysis.py
│   │   │   │   ├── 0002_import_references.py
│   │   │   │   ├── 0003_semantic_index.py
│   │   │   │   ├── 0004_agent_runs.py
│   │   │   │   ├── 0005_draft_workspaces.py
│   │   │   │   └── 0006_test_executions.py
│   │   │   ├── env.py
│   │   │   └── script.py.mako
│   │   ├── tests/
│   │   │   ├── fixtures/
│   │   │   │   └── sample/
│   │   │   │       ├── auth.py
│   │   │   │       ├── client.ts
│   │   │   │       └── view.jsx
│   │   │   ├── conftest.py
│   │   │   ├── test_anthropic.py
│   │   │   ├── test_agent.py
│   │   │   ├── test_archive.py
│   │   │   ├── test_dependencies.py
│   │   │   ├── test_github.py
│   │   │   ├── test_health.py
│   │   │   ├── test_parsers.py
│   │   │   ├── test_qa.py
│   │   │   ├── test_repositories.py
│   │   │   ├── test_retrieval.py
│   │   │   ├── test_sandbox.py
│   │   │   ├── test_sandbox_live.py
│   │   │   └── test_workspace.py
│   │   ├── alembic.ini
│   │   ├── pyproject.toml
│   │   └── requirements-dev.lock
│   └── web/
│       ├── src/
│       │   ├── app/
│       │   │   ├── api/
│       │   │   │   ├── health/
│       │   │   │   │   └── route.ts
│       │   │   │   └── repositories/
│       │   │   │       └── [[...path]]/
│       │   │   │           └── route.ts
│       │   │   ├── globals.css
│       │   │   ├── layout.tsx
│       │   │   └── page.tsx
│       │   ├── components/
│       │   │   ├── api-status.tsx
│       │   │   ├── code-viewer.tsx
│       │   │   ├── dependency-graph.tsx
│       │   │   ├── file-tree.tsx
│       │   │   ├── graph-canvas.tsx
│       │   │   ├── repository-agent.tsx
│       │   │   ├── repository-ask.tsx
│       │   │   ├── repository-explorer.tsx
│       │   │   ├── retrieval-diagnostics.tsx
│       │   │   ├── test-review.tsx
│       │   │   ├── workspace-review.tsx
│       │   │   └── workspace.tsx
│       │   └── lib/
│       │       ├── agent.ts
│       │       ├── file-tree.ts
│       │       ├── graph.ts
│       │       ├── highlight.ts
│       │       ├── proxy-policy.ts
│       │       ├── qa.ts
│       │       ├── repositories.ts
│       │       └── test-runs.ts
│       ├── tests/
│       │   ├── agent.test.ts
│       │   ├── explorer.test.ts
│       │   ├── graph.test.ts
│       │   ├── qa.test.ts
│       │   └── test-runs.test.ts
│       ├── eslint.config.mjs
│       ├── next-env.d.ts
│       ├── next.config.ts
│       ├── package.json
│       ├── postcss.config.mjs
│       └── tsconfig.json
├── docs/
│   ├── mcp-architecture.md
│   ├── development.md
│   ├── evaluation-m4-offline.json
│   ├── structure.md
│   └── verification.md
├── sandbox/
│   ├── node.Dockerfile
│   ├── node_runner.mjs
│   ├── python.Dockerfile
│   └── unittest_runner.py
├── .env.example
├── .gitignore
├── README.md
├── compose.yaml
├── package-lock.json
└── package.json
```
