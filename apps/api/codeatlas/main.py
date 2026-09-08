from contextlib import asynccontextmanager

from fastapi import FastAPI

from codeatlas.api.health import router
from codeatlas.core.config import Settings
from codeatlas.core.database import create_database_engine


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database = create_database_engine(settings or Settings())
        try:
            yield
        finally:
            app.state.database.dispose()

    app = FastAPI(title="CodeAtlas API", version="0.1.0", lifespan=lifespan)
    app.include_router(router, prefix="/api")
    return app


app = create_app()
