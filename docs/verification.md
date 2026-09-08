# Milestone 0 verification

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
