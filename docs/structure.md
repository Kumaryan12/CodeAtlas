# Source tree

Tracked source/configuration/documentation files. Local `.env`, dependencies, build output, database volumes, and temporary workspaces are excluded.

```text
CodeAtlas/
├── apps/
│   ├── api/
│   │   ├── codeatlas/
│   │   │   ├── api/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── health.py
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
│   │   │   ├── schemas/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── graph.py
│   │   │   │   └── repository.py
│   │   │   ├── services/
│   │   │   │   ├── __init__.py
│   │   │   │   └── import_repository.py
│   │   │   ├── __init__.py
│   │   │   └── main.py
│   │   ├── migrations/
│   │   │   ├── versions/
│   │   │   │   ├── 0001_repository_analysis.py
│   │   │   │   └── 0002_import_references.py
│   │   │   ├── env.py
│   │   │   └── script.py.mako
│   │   ├── tests/
│   │   │   ├── fixtures/
│   │   │   │   └── sample/
│   │   │   │       ├── auth.py
│   │   │   │       ├── client.ts
│   │   │   │       └── view.jsx
│   │   │   ├── test_archive.py
│   │   │   ├── test_dependencies.py
│   │   │   ├── test_github.py
│   │   │   ├── test_health.py
│   │   │   ├── test_parsers.py
│   │   │   └── test_repositories.py
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
│       │   │   ├── repository-explorer.tsx
│       │   │   └── workspace.tsx
│       │   └── lib/
│       │       ├── file-tree.ts
│       │       ├── graph.ts
│       │       ├── highlight.ts
│       │       ├── proxy-policy.ts
│       │       └── repositories.ts
│       ├── tests/
│       │   ├── explorer.test.ts
│       │   └── graph.test.ts
│       ├── eslint.config.mjs
│       ├── next-env.d.ts
│       ├── next.config.ts
│       ├── package.json
│       ├── postcss.config.mjs
│       └── tsconfig.json
├── docs/
│   ├── development.md
│   ├── structure.md
│   └── verification.md
├── .env.example
├── .gitignore
├── README.md
├── compose.yaml
├── package-lock.json
└── package.json
```
