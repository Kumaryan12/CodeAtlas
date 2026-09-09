import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from codeatlas.api.health import router as health_router
from codeatlas.api.qa import router as qa_router
from codeatlas.api.repositories import router as repository_router
from codeatlas.core.body_limit import ImportBodyLimit
from codeatlas.core.config import Settings
from codeatlas.core.database import create_database_engine
from codeatlas.core.errors import DomainError
from codeatlas.core.logging import configure_logging

logger = logging.getLogger("codeatlas.api")


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        app.state.settings = settings or Settings()
        app.state.database = create_database_engine(app.state.settings)
        app.state.import_lock = threading.Lock()
        app.state.ai_lock = threading.Lock()
        try:
            yield
        finally:
            app.state.database.dispose()

    app = FastAPI(title="CodeAtlas API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(ImportBodyLimit)
    app.include_router(health_router, prefix="/api")
    app.include_router(repository_router, prefix="/api")
    app.include_router(qa_router, prefix="/api")

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logger.error("database_operation_failed")
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": "Database unavailable or schema missing. Run migrations and retry.",
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Do not reflect arbitrary request bodies or exception contexts back to clients.
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "Invalid request. Check the repository URL, IDs, or pagination.",
                }
            },
        )

    return app


app = create_app()
