from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, load_only

from codeatlas.agents.runner import execute_run
from codeatlas.agents.tools import ReadTools
from codeatlas.ai.investigator import InvestigationProvider, get_investigator
from codeatlas.api.qa import ready_repository
from codeatlas.api.repositories import Database
from codeatlas.core.errors import DomainError
from codeatlas.models.repository import AgentRun, Repository
from codeatlas.schemas.agent import (
    InvestigationRequest,
    InvestigationResult,
    RunList,
    RunResponse,
    RunSummary,
)
from codeatlas.schemas.qa import Citation

router = APIRouter(prefix="/repositories", tags=["investigations"])


def investigator_dependency(request: Request) -> InvestigationProvider:
    return get_investigator(request.app.state.settings)


Investigator = Annotated[InvestigationProvider, Depends(investigator_dependency)]


def run_response(session, run):
    result = None
    if run.result is not None:
        repository = session.get(Repository, run.repository_id)
        reader = ReadTools(session, repository, None, None)
        citations = []
        for reference in run.result["citations"]:
            file = reader.file(reference["file_id"])
            lines = [line.removesuffix("\r") for line in file.source.split("\n")]
            citations.append(
                Citation(
                    **reference,
                    source="\n".join(lines[reference["start_line"] - 1 : reference["end_line"]]),
                )
            )
        result = InvestigationResult(
            status=run.result["status"], claims=run.result["claims"], citations=citations
        )
    return RunResponse(
        **RunSummary.model_validate(run, from_attributes=True).model_dump(),
        plan=run.plan,
        steps=run.steps,
        result=result,
    )


@router.post("/{repository_id}/agent-runs", response_model=RunResponse, status_code=202)
def start_investigation(
    repository_id: UUID,
    payload: InvestigationRequest,
    request: Request,
    session: Database,
    provider: Investigator,
    background: BackgroundTasks,
):
    repository = ready_repository(session, repository_id)
    lock = request.app.state.ai_lock
    if not lock.acquire(blocking=False):
        raise DomainError("ai_busy", "Another AI operation is running. Try again shortly.", 409)
    try:
        run = AgentRun(
            repository_id=repository.id,
            task=payload.task,
            model=request.app.state.settings.answer_model,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        response = run_response(session, run)
        background.add_task(
            execute_run,
            request.app.state.database,
            run.id,
            request.app.state.settings,
            provider,
            lock,
        )
        return response
    except Exception:
        lock.release()
        raise


@router.get("/{repository_id}/agent-runs", response_model=RunList)
def list_runs(
    repository_id: UUID,
    session: Database,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    ready_repository(session, repository_id)
    condition = AgentRun.repository_id == str(repository_id)
    rows = session.scalars(
        select(AgentRun)
        .options(
            load_only(
                *[getattr(AgentRun, name) for name in RunSummary.model_fields], raiseload=True
            )
        )
        .where(condition)
        .order_by(AgentRun.created_at.desc(), AgentRun.id)
        .offset(offset)
        .limit(limit)
    )
    return RunList(
        items=[RunSummary.model_validate(row, from_attributes=True) for row in rows],
        total=session.scalar(select(func.count()).select_from(AgentRun).where(condition)) or 0,
    )


@router.get("/{repository_id}/agent-runs/{run_id}", response_model=RunResponse)
def get_run(repository_id: UUID, run_id: UUID, session: Database):
    ready_repository(session, repository_id)
    run = session.scalar(
        select(AgentRun).where(
            AgentRun.id == str(run_id), AgentRun.repository_id == str(repository_id)
        )
    )
    if run is None:
        raise DomainError("run_not_found", "Investigation was not found in this snapshot.", 404)
    return run_response(session, run)


def recover_interrupted(engine):
    # Single-worker MVP: no durable job queue and no automatic reruns after a restart.
    try:
        with Session(engine) as session:
            for run in session.scalars(select(AgentRun).where(AgentRun.status == "running")):
                run.status = "interrupted"
                run.error_code = "server_restarted"
                run.error_message = "The API restarted before this investigation finished."
                run.finished_at = datetime.now(UTC)
                run.steps = [
                    {
                        **step,
                        "status": "failed",
                        "summary": "Interrupted by API restart.",
                        "error_code": "server_restarted",
                    }
                    if step["status"] == "running"
                    else step
                    for step in run.steps
                ]
            session.commit()
    except SQLAlchemyError:
        # Health must remain available before initial migrations or when the DB is down.
        pass
