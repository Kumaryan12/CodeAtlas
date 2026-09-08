import logging
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from codeatlas.core.database import check_database

router = APIRouter(tags=["health"])
logger = logging.getLogger("codeatlas.health")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["codeatlas-api"] = "codeatlas-api"


class ReadyResponse(BaseModel):
    status: Literal["ready"] = "ready"
    database: Literal["connected"] = "connected"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/ready", response_model=ReadyResponse, responses={503: {"model": ErrorResponse}})
def ready(request: Request) -> ReadyResponse | JSONResponse:
    try:
        check_database(request.app.state.database)
    except SQLAlchemyError:
        # Never log connection exception text, which may include credentials.
        logger.warning("database_unavailable")
        error = ErrorResponse(
            error=ErrorDetail(
                code="database_unavailable", message="Database is unavailable. Try again shortly."
            )
        )
        return JSONResponse(status_code=503, content=error.model_dump())
    return ReadyResponse()
