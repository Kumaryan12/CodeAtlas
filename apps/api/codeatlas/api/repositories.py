from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer, load_only

from codeatlas.core.errors import DomainError
from codeatlas.models.repository import CodeSymbol, Repository, RepositoryFile
from codeatlas.parsers.types import Symbol
from codeatlas.schemas.repository import (
    FileDetail,
    FileList,
    FileResponse,
    ImportRequest,
    RepositoryList,
    RepositoryResponse,
    SymbolList,
    SymbolResponse,
)
from codeatlas.services.import_repository import import_repository

router = APIRouter(prefix="/repositories", tags=["repositories"])


def database_session(request: Request):
    with Session(request.app.state.database, expire_on_commit=False) as session:
        yield session


Database = Annotated[Session, Depends(database_session)]


def get_repository(session: Session, repository_id: UUID) -> Repository:
    repository = session.get(Repository, str(repository_id))
    if repository is None:
        raise DomainError("repository_not_found", "Repository snapshot was not found.", 404)
    return repository


@router.post("", response_model=RepositoryResponse, status_code=201)
def create_repository(payload: ImportRequest, request: Request, session: Database):
    # The synchronous MVP intentionally supports one import per API process.
    if not request.app.state.import_lock.acquire(blocking=False):
        raise DomainError(
            "import_busy", "Another repository is being imported. Try again shortly.", 409
        )
    try:
        return import_repository(session, payload.url, request.app.state.settings)
    finally:
        request.app.state.import_lock.release()


@router.get("", response_model=RepositoryList)
def list_repositories(
    session: Database, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
):
    items = session.scalars(
        select(Repository)
        .order_by(Repository.created_at.desc(), Repository.id)
        .limit(limit)
        .offset(offset)
    )
    return RepositoryList(
        items=[RepositoryResponse.model_validate(item) for item in items],
        total=session.scalar(select(func.count()).select_from(Repository)) or 0,
    )


@router.get("/{repository_id}", response_model=RepositoryResponse)
def repository_detail(repository_id: UUID, session: Database):
    return get_repository(session, repository_id)


@router.get("/{repository_id}/files", response_model=FileList)
def list_files(
    repository_id: UUID,
    session: Database,
    limit: int = Query(1000, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    repository = get_repository(session, repository_id)
    files = session.scalars(
        select(RepositoryFile)
        .options(
            defer(RepositoryFile.source, raiseload=True),
            defer(RepositoryFile.imports, raiseload=True),
        )
        .where(RepositoryFile.repository_id == repository.id)
        .order_by(RepositoryFile.path)
        .limit(limit)
        .offset(offset)
    )
    return FileList(
        items=[FileResponse.model_validate(file) for file in files], total=repository.file_count
    )


@router.get("/{repository_id}/files/{file_id}", response_model=FileDetail)
def file_detail(repository_id: UUID, file_id: UUID, session: Database):
    get_repository(session, repository_id)
    file = session.scalar(
        select(RepositoryFile).where(
            RepositoryFile.id == str(file_id), RepositoryFile.repository_id == str(repository_id)
        )
    )
    if file is None:
        raise DomainError("file_not_found", "File was not found in this repository snapshot.", 404)
    symbols = session.scalars(
        select(CodeSymbol)
        .where(CodeSymbol.file_id == file.id)
        .order_by(CodeSymbol.start_line, CodeSymbol.id)
    )
    return FileDetail(
        **FileResponse.model_validate(file).model_dump(),
        source=file.source,
        imports=file.imports,
        symbols=[Symbol.model_validate(s, from_attributes=True) for s in symbols],
    )


@router.get("/{repository_id}/symbols", response_model=SymbolList)
def list_symbols(
    repository_id: UUID,
    session: Database,
    file_id: UUID | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    get_repository(session, repository_id)
    conditions = [RepositoryFile.repository_id == str(repository_id)]
    if file_id:
        conditions.append(CodeSymbol.file_id == str(file_id))
    query = (
        select(CodeSymbol, RepositoryFile)
        .join(RepositoryFile)
        .options(
            load_only(
                RepositoryFile.id, RepositoryFile.path, RepositoryFile.language, raiseload=True
            )
        )
        .where(*conditions)
    )
    rows = session.execute(
        query.order_by(RepositoryFile.path, CodeSymbol.start_line, CodeSymbol.id)
        .limit(limit)
        .offset(offset)
    )
    total = (
        session.scalar(
            select(func.count()).select_from(CodeSymbol).join(RepositoryFile).where(*conditions)
        )
        or 0
    )
    return SymbolList(
        items=[
            SymbolResponse(
                **Symbol.model_validate(symbol, from_attributes=True).model_dump(),
                file_id=file.id,
                file_path=file.path,
                language=file.language,
            )
            for symbol, file in rows
        ],
        total=total,
    )
