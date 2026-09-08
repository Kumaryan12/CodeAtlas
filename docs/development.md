# Development guide

## Architecture and decisions

The browser renders the Next.js workspace and requests its same-origin health route. Next.js forwards that fixed request to FastAPI. FastAPI owns database access through SQLAlchemy and psycopg. PostgreSQL runs independently in Compose. The backend uses synchronous endpoints for blocking database operations, which FastAPI runs in its thread pool.

| Choice | Why | Alternative and trade-off | Interview question |
| --- | --- | --- | --- |
| npm workspaces with `apps/web` and `apps/api` | One repository, independent application runtimes, little orchestration | Turborepo can add caching later; extra setup is not useful yet | Why a monorepo rather than separate repos? |
| Next.js App Router | Typed React application and a small server boundary | A Vite SPA is simpler but needs a separate proxy/deployment arrangement | What belongs on the server versus in the browser? |
| Same-origin health proxy | Keep upstream configuration server-side and bound network timeout | Direct browser-to-API calls avoid a hop but need CORS and a public API URL | What does a backend-for-frontend boundary buy us? |
| FastAPI application factory and lifespan | Isolated tests and explicit pool disposal | Import-time global connections make lifecycle/testing harder | Why manage resources during application lifespan? |
| SQLAlchemy + PostgreSQL | Relational constraints and transactions fit repository/file/symbol relationships | SQLite is easier locally but differs from the intended deployment database | How would you keep a repository and its files consistent? |
| Separate liveness and readiness | An unavailable database should fail readiness without making liveness fail | One combined endpoint is simpler but can trigger unnecessary process restarts | When should an orchestrator restart versus stop routing traffic? |
| No initial tables | Persist only when requirements establish entities and constraints | Creating every future entity now locks in speculative schemas | When should you introduce a database migration? |

The frontend follows the [Next.js installation guidance](https://nextjs.org/docs/app/getting-started/installation). Backend configuration and lifecycle follow [FastAPI settings](https://fastapi.tiangolo.com/advanced/settings/) and [lifespan guidance](https://fastapi.tiangolo.com/advanced/events/).

## Source tree

Generated dependencies, local `.env`, caches, and build output are omitted.

```text
CodeAtlas/
├── .env.example
├── .gitignore
├── README.md
├── compose.yaml
├── package.json
├── package-lock.json
├── apps/
│   ├── api/
│   │   ├── pyproject.toml
│   │   ├── requirements-dev.lock
│   │   ├── codeatlas/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── api/
│   │   │   │   ├── __init__.py
│   │   │   │   └── health.py
│   │   │   └── core/
│   │   │       ├── __init__.py
│   │   │       ├── config.py
│   │   │       └── database.py
│   │   └── tests/
│   │       └── test_health.py
│   └── web/
│       ├── package.json
│       ├── next-env.d.ts
│       ├── next.config.ts
│       ├── tsconfig.json
│       ├── eslint.config.mjs
│       ├── postcss.config.mjs
│       └── src/
│           ├── app/
│           │   ├── globals.css
│           │   ├── layout.tsx
│           │   ├── page.tsx
│           │   └── api/health/route.ts
│           └── components/api-status.tsx
└── docs/
    ├── development.md
    └── verification.md
```

## Working conventions

- Implement one small milestone at a time. Describe changes before editing; verify behavior before calling it done.
- Commit and push to `Kumaryan12/CodeAtlas` at meaningful checkpoints. Inspect staged changes and never include local configuration, credentials, dependencies, or generated output.
- Add layers only when a real use case requires them. Domain persistence, parsing, retrieval, AI, and agent modules will be introduced with their milestones.
- Do not execute untrusted repositories during ingestion. Future execution must use a sandbox with explicit resource limits.
- Write schema changes through Alembic migrations when the first tables are introduced.
- Keep future model providers behind interfaces, and enforce tool permissions outside the model. No AI code is required now.

## Intentional deferrals

This milestone has no authentication, database entities, migrations, ingestion, parser, queue, graph, embeddings, AI provider, agent, deployment, or CI. Database readiness unit tests mock the database boundary; a real PostgreSQL check is a separate integration check. UI behavior is small enough for lint/type/build plus runtime smoke checks at this stage. Add dedicated frontend interaction tests once repository state and user inputs arrive.

## Proposed Milestone 1

Deliver public GitHub ingestion and deterministic analysis in reviewable slices:

1. URL validation and bounded archive download into isolated workspaces, rejecting unsafe paths and links, enforcing timeouts and compressed/uncompressed byte and file-count limits. Never execute code.
2. Scan supported source files; skip generated directories, binaries, oversized files, and unsupported languages, reporting skip counts and partial failures.
3. Define normalized symbols and parser contracts, implement Python AST and justified JS/TS Tree-sitter parsing with small fixture repositories.
4. Add `Repository`, `RepositoryFile`, and `CodeSymbol` models with Alembic migrations, status/error fields and transaction boundaries. No speculative user, chat, agent, or embedding tables.
5. Add typed repository/file/symbol API routes and connect import, explorer, statistics, and symbol views to real data.
6. Test malformed URLs, unavailable repositories, traversal and archive bombs, ignore rules, malformed source, parser behavior, and API errors.

Dependency graphs are Milestone 2. Milestone 1 begins only after the user's next instruction.

## Dependency compatibility note

ESLint 9.39.5 is intentionally retained: ESLint 10.10.0 fails in the React plugin supplied by the current Next.js configuration (`contextOrFilename.getFilename is not a function`). npm reports ESLint 9 as unsupported. Upgrade when that plugin supports ESLint 10, and remove this documented tooling debt after lint passes on the newer major. Backend tests currently produce upstream Starlette/httpx and AnyIO deprecation warnings; keep them visible and revisit the test-client dependency during upgrades.
