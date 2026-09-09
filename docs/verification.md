# Verification record

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
