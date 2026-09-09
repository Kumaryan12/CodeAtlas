from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from codeatlas.ai.provider import AIProvider, get_provider
from codeatlas.api.repositories import Database, get_repository
from codeatlas.core.errors import DomainError
from codeatlas.schemas.qa import AskRequest, AskResponse, IndexStatus
from codeatlas.services.qa import ask, build_index, index_status

router = APIRouter(prefix="/repositories", tags=["questions"])


def provider_dependency(request: Request) -> AIProvider:
    return get_provider(request.app.state.settings)


Provider = Annotated[AIProvider, Depends(provider_dependency)]


def ready_repository(session, repository_id):
    repository = get_repository(session, repository_id)
    if repository.status not in {"ready", "partial"}:
        raise DomainError(
            "repository_not_ready", "A completed repository snapshot is required.", 409
        )
    return repository


@router.get("/{repository_id}/index", response_model=IndexStatus)
def status(repository_id: UUID, request: Request, session: Database):
    return index_status(
        session, ready_repository(session, repository_id), request.app.state.settings
    )


@router.post("/{repository_id}/index", response_model=IndexStatus)
def index(repository_id: UUID, request: Request, session: Database, provider: Provider):
    repository = ready_repository(session, repository_id)
    if not request.app.state.ai_lock.acquire(blocking=False):
        raise DomainError("ai_busy", "Another AI operation is running. Try again shortly.", 409)
    try:
        return build_index(session, repository, request.app.state.settings, provider)
    finally:
        request.app.state.ai_lock.release()


@router.post("/{repository_id}/ask", response_model=AskResponse)
def question(
    repository_id: UUID,
    payload: AskRequest,
    request: Request,
    session: Database,
    provider: Provider,
):
    repository = ready_repository(session, repository_id)
    if not request.app.state.ai_lock.acquire(blocking=False):
        raise DomainError("ai_busy", "Another AI operation is running. Try again shortly.", 409)
    try:
        return ask(session, repository, payload.question, request.app.state.settings, provider)
    finally:
        request.app.state.ai_lock.release()
