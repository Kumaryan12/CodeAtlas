# CodeAtlas

A codebase intelligence platform built incrementally around deterministic source analysis, grounded retrieval, and reviewable engineering actions.

**Current milestone: 0 — project foundation.** This is a working application shell, not yet a repository analyzer. Repository ingestion, parsing, graphs, AI, and agents are not implemented.

## What works

- Next.js App Router workspace with TypeScript and Tailwind CSS; responsive empty state and live API connectivity check.
- FastAPI service with typed health responses, database readiness, and OpenAPI documentation.
- Environment-based configuration and a lazy SQLAlchemy PostgreSQL connection pool.
- Local PostgreSQL Compose service with a persistent volume and health check.
- Backend behavior tests, Python lint/format checks, and frontend lint/type/build checks.

## Prerequisites

Node.js 22.13+ (or a newer supported Node release), npm, Python 3.12+, and Docker with Compose for PostgreSQL. Development was verified with Node 26 and Python 3.14 on macOS. No LLM keys or GitHub tokens are needed.

## Setup

Run from the repository root:

```sh
cp .env.example .env
npm ci
python3 -m venv apps/api/.venv
apps/api/.venv/bin/python -m pip install -r apps/api/requirements-dev.lock
apps/api/.venv/bin/python -m pip install --no-deps -e apps/api
```

The Python lock file pins the tested development environment, including transitive dependencies. It is a pip version snapshot, not a cross-platform hash lock. For deliberate dependency upgrades, install `-e 'apps/api[dev]'`, rerun checks, and regenerate with `pip freeze --exclude codeatlas-api` using the project virtual environment.

Start Docker Desktop (or your Docker daemon), then:

```sh
docker compose up -d postgres
```

In terminal 1, from the root:

```sh
apps/api/.venv/bin/uvicorn codeatlas.main:app --app-dir apps/api --reload --host 127.0.0.1 --port 8000
```

In terminal 2, from the root:

```sh
npm run dev
```

Open http://127.0.0.1:3000. API docs: http://127.0.0.1:8000/docs.

The web and API applications can start without PostgreSQL. Database readiness will return 503 until PostgreSQL is available. The workspace indicator reports API liveness, not database readiness.

For a production-mode frontend smoke test: `npm run build && npm start`. This foundation is for local development; deployment, authentication, and production hardening are future work.

## Configuration

Root `.env` is read by Compose, FastAPI, and the Next.js configuration. Restart applications after changes. Do not commit it.

| Variable | Purpose |
| --- | --- |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Local Compose database initialization |
| `POSTGRES_PORT` | Host PostgreSQL port (default 5432) |
| `CODEATLAS_DATABASE_URL` | SQLAlchemy connection URL using `postgresql+psycopg` |
| `API_BASE_URL` | Server-only Next.js upstream API address |

If you change the host port or credentials, also update `CODEATLAS_DATABASE_URL`. Compose initialization variables apply only when its data volume is first created; changing `.env` does not update an existing database password. Do not delete an existing volume unless its data is disposable. The checked-in example credentials are exclusively for local development.

## API

| Route | Behavior |
| --- | --- |
| `GET /api/health` | 200: process liveness; no database access |
| `GET /api/ready` | 200 after `SELECT 1`; 503 with `error.code=database_unavailable` on database failure |
| `GET /docs` | Interactive OpenAPI documentation |
| `GET /openapi.json` | Machine-readable API schema |

The frontend's own `/api/health` route proxies the fixed backend health path with a four-second timeout, returning a sanitized 503 if the API is unreachable or returns an invalid response. Browsers use the same origin; no permissive CORS configuration is needed.

## Verification

```sh
apps/api/.venv/bin/pytest apps/api/tests -q
apps/api/.venv/bin/ruff check apps/api
apps/api/.venv/bin/ruff format --check apps/api
npm run lint
npm run typecheck
npm run build
docker compose config --quiet
curl -i http://127.0.0.1:8000/api/health
curl -i http://127.0.0.1:8000/api/ready
curl -i http://127.0.0.1:3000/api/health
```

Manual checks:

1. Open the workspace; check the empty state and the API online indicator.
2. Stop FastAPI and press the connection refresh button. Expect API offline; restart FastAPI and retry to restore online status.
3. Check `/api/ready` with PostgreSQL available (200) and stopped (503). The response must not include connection details.
4. Resize to a narrow viewport; navigation and roadmap cards should stack without horizontal scrolling.
5. Open `/docs` and try both health endpoints.

See [development notes](docs/development.md) for decisions, trade-offs, milestone boundaries, and the exact source tree. See [verification record](docs/verification.md) for checks performed in this environment.

## Security and limitations

No repository code is downloaded or executed in Milestone 0. Development servers and the Compose database bind only to loopback. Database connection errors are sanitized, database URLs are represented as secrets, and `.env` and future untrusted workspaces are ignored by Git. This is not a complete production security boundary: authentication, request limits, structured request tracing, and sandboxed execution are not implemented.

There are no database tables yet. Milestone 1 will introduce Alembic migrations with the first entities; application startup will not call `create_all`. No vector database, task queue, empty agent framework, or React Flow dependency is installed before it is useful.

## Roadmap

0. **Foundation** — web/API shells, configuration, health, setup.
1. **Deterministic repository analysis** — safe public GitHub ingestion, file scanning, Python/JS/TS symbols, persisted metadata, file explorer and statistics.
2. **Dependency graph** — import resolution and React Flow visualization.
3. **Grounded Q&A** — semantic code indexing, provider abstraction, source citations.
4. **Retrieval quality** — hybrid search, graph expansion, diagnostics and evaluation.
5. **Read-only agent** — constrained tools and structured execution traces.
6. **Reviewable edits** — isolated workspaces and diffs.
7. **Sandboxed tests** — bounded execution and retries.
8. **Approved pull requests** — explicit human approval before remote changes.
