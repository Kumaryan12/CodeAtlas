from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, load_only

from codeatlas.agents.runner import execute_run
from codeatlas.agents.tools import ReadTools
from codeatlas.agents.workspace import DraftWorkspace
from codeatlas.ai.investigator import InvestigationProvider, get_investigator
from codeatlas.ai.usage import summarize_usage
from codeatlas.api.qa import ready_repository
from codeatlas.api.repositories import Database
from codeatlas.core.errors import DomainError
from codeatlas.models.repository import AgentRun, Repository, TestExecution
from codeatlas.sandbox.docker import require_sandbox
from codeatlas.sandbox.service import execute_manual_test, reserve_test
from codeatlas.schemas.agent import (
    InvestigationRequest,
    InvestigationResult,
    RunList,
    RunResponse,
    RunSummary,
    TestRequest,
    TestResponse,
    WorkspaceDiff,
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
        usage_summary=summarize_usage(run.steps),
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
    if payload.test_profile:
        require_sandbox(request.app.state.settings, payload.test_profile)
    lock = request.app.state.ai_lock
    if not lock.acquire(blocking=False):
        raise DomainError("ai_busy", "Another AI operation is running. Try again shortly.", 409)
    try:
        run = AgentRun(
            repository_id=repository.id,
            task=payload.task,
            mode=payload.mode,
            test_profile=payload.test_profile,
            model=request.app.state.settings.reasoning_model,
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


@router.get("/{repository_id}/agent-runs/{run_id}/diff", response_model=WorkspaceDiff)
def get_workspace_diff(repository_id: UUID, run_id: UUID, session: Database):
    repository = ready_repository(session, repository_id)
    run = session.scalar(
        select(AgentRun).where(AgentRun.id == str(run_id), AgentRun.repository_id == repository.id)
    )
    if run is None or run.mode != "edit":
        raise DomainError(
            "workspace_not_found", "Draft workspace was not found in this snapshot.", 404
        )
    return DraftWorkspace(session, run, repository).diff()


def scoped_draft(session, repository_id, run_id):
    ready_repository(session, repository_id)
    run = session.scalar(
        select(AgentRun).where(
            AgentRun.id == str(run_id), AgentRun.repository_id == str(repository_id)
        )
    )
    if run is None or run.mode != "edit":
        raise DomainError("workspace_not_found", "Draft was not found in this snapshot.", 404)
    return run


@router.get("/{repository_id}/agent-runs/{run_id}/test-runs", response_model=list[TestResponse])
def list_tests(repository_id: UUID, run_id: UUID, session: Database):
    run = scoped_draft(session, repository_id, run_id)
    return [
        TestResponse.model_validate(test, from_attributes=True)
        for test in session.scalars(
            select(TestExecution)
            .where(TestExecution.run_id == run.id)
            .order_by(TestExecution.created_at, TestExecution.id)
        )
    ]


@router.post(
    "/{repository_id}/agent-runs/{run_id}/test-runs", response_model=TestResponse, status_code=202
)
def start_test(
    repository_id: UUID,
    run_id: UUID,
    payload: TestRequest,
    request: Request,
    session: Database,
    background: BackgroundTasks,
):
    run = scoped_draft(session, repository_id, run_id)
    if run.status == "running":
        raise DomainError(
            "draft_busy", "Wait for the agent to finish before manually testing its draft.", 409
        )
    lock = request.app.state.ai_lock
    if not lock.acquire(blocking=False):
        raise DomainError("ai_busy", "Another AI or test operation is running.", 409)
    try:
        image = require_sandbox(request.app.state.settings, payload.profile)
        test = reserve_test(session, run, payload.profile, payload.workspace_digest, image)
        response = TestResponse.model_validate(test, from_attributes=True)
        background.add_task(
            execute_manual_test,
            request.app.state.database,
            test.id,
            request.app.state.settings,
            lock,
        )
        return response
    except Exception:
        lock.release()
        raise


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
            for test in session.scalars(
                select(TestExecution).where(TestExecution.status == "running")
            ):
                test.status = "interrupted"
                test.error_code = "server_restarted"
                test.finished_at = datetime.now(UTC)
            session.commit()
    except SQLAlchemyError:
        # Health must remain available before initial migrations or when the DB is down.
        pass
