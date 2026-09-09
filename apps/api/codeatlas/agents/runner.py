"""A bounded decision/read loop. Durable trace writes are separate from repository reads."""

import json
import logging
import time
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from codeatlas.agents.tools import ReadTools
from codeatlas.core.errors import DomainError
from codeatlas.models.repository import AgentRun, Repository
from codeatlas.schemas.agent import AgentDecision, AgentStep

MAX_TOOLS = 5
MAX_DECISIONS = 6
MAX_SECONDS = 90
MAX_CONTEXT_BYTES = 48_000
logger = logging.getLogger("codeatlas.agent")


def append_step(session, run, kind, action):
    step = AgentStep(
        number=len(run.steps) + 1,
        kind=kind,
        action=action,
        status="running",
        started_at=datetime.now(UTC).isoformat(),
        duration_ms=0,
        summary="",
    )
    run.steps = [*run.steps, step.model_dump()]
    session.commit()
    return time.monotonic()


def finish_step(session, run, started, summary, error_code=None):
    step = {
        **run.steps[-1],
        "status": "failed" if error_code else "completed",
        "summary": summary,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "error_code": error_code,
    }
    run.steps = [*run.steps[:-1], step]
    session.commit()


def finish_run(session, run, status, code=None, message=None):
    run.status, run.error_code, run.error_message = status, code, message
    run.finished_at = datetime.now(UTC)
    session.commit()
    logger.info(
        "investigation_finished",
        extra={
            "repository_id": run.repository_id,
            "run_id": run.id,
            "status": status,
            "code": code,
        },
    )


def tool_summary(action, result):
    if action == "list_files":
        return f"Listed {len(result['files'])} of {result['total']} matching source files."
    if action == "search_code":
        return f"Retrieved {len(result['matches'])} excerpts: " + ", ".join(
            row["id"] for row in result["matches"]
        )
    if action == "find_symbol":
        return f"Found {result['total']} symbols; returned {len(result['symbols'])} locations."
    if action == "read_file":
        row = result["excerpt"]
        return f"Read {row['file_path'][:200]}:{row['start_line']}–{row['end_line']} ({row['id']})."
    return f"Inspected {result['import_count']} imports and {result['importer_count']} importers."


def run_loop(session, run, settings, provider):
    repository = session.get(Repository, run.repository_id)
    tools = ReadTools(session, repository, settings, provider)
    observations = []
    started = time.monotonic()
    attempts = 0
    seen = set()
    for _ in range(MAX_DECISIONS):
        if time.monotonic() - started >= MAX_SECONDS:
            return finish_run(
                session, run, "limited", "run_timeout", "Investigation reached its time budget."
            )
        state = {
            "task": run.task,
            "repository": repository.full_name,
            "commit_sha": repository.commit_sha,
            "plan": run.plan,
            "observations": observations,
            "evidence": [c.model_dump() for c in tools.evidence.values()],
            "remaining_tools": MAX_TOOLS - attempts,
        }
        if len(json.dumps(state, ensure_ascii=False).encode()) > MAX_CONTEXT_BYTES:
            return finish_run(
                session,
                run,
                "limited",
                "context_limit",
                "Investigation reached its context budget.",
            )
        step_started = append_step(session, run, "model", "choose_next_step")
        try:
            decision = AgentDecision.model_validate(provider.decide(state))
        except ValidationError as exc:
            raise DomainError(
                "invalid_agent_decision", "The model proposed an invalid investigation step.", 502
            ) from exc
        if not run.plan:
            run.plan = decision.plan
        finish_step(session, run, step_started, decision.summary)
        if time.monotonic() - started >= MAX_SECONDS:
            return finish_run(
                session, run, "limited", "run_timeout", "Investigation reached its time budget."
            )
        arguments = decision.arguments.model_dump(exclude_none=True)
        if decision.action == "finish":
            answer = decision.answer
            if arguments or answer is None:
                raise DomainError(
                    "invalid_agent_finish", "The model returned an invalid final result.", 502
                )
            used = {key for claim in answer.claims for key in claim.citation_ids}
            if (
                not used <= tools.evidence.keys()
                or (answer.status == "answered" and not answer.claims)
                or (answer.status == "insufficient_context" and answer.claims)
            ):
                raise DomainError(
                    "invalid_citations",
                    "The investigation returned unsupported evidence references.",
                    502,
                )
            run.result = {
                **answer.model_dump(),
                "citations": [
                    c.model_dump(exclude={"source"})
                    for key, c in tools.evidence.items()
                    if key in used
                ],
            }
            return finish_run(session, run, "completed")
        if decision.answer is not None:
            raise DomainError(
                "invalid_agent_decision", "An intermediate step cannot contain a final answer.", 502
            )
        if attempts >= MAX_TOOLS:
            return finish_run(
                session, run, "limited", "step_limit", "Investigation reached its read-tool limit."
            )
        signature = (decision.action, json.dumps(arguments, sort_keys=True))
        attempts += 1
        step_started = append_step(session, run, "read", decision.action)
        try:
            if signature in seen:
                raise DomainError(
                    "repeated_tool_call",
                    "This read was already attempted. Use its result or finish.",
                    422,
                )
            seen.add(signature)
            result = tools.execute(decision.action, arguments)
        except DomainError as exc:
            result = {"error": {"code": exc.code, "message": exc.message}}
            finish_step(session, run, step_started, exc.message, exc.code)
        else:
            finish_step(
                session,
                run,
                step_started,
                tool_summary(decision.action, result),
            )
        observations.append({"action": decision.action, "arguments": arguments, "result": result})
    finish_run(session, run, "limited", "step_limit", "Investigation reached its decision limit.")


def execute_run(engine, run_id, settings, provider, lock):
    try:
        with Session(engine, expire_on_commit=False) as session:
            run = session.get(AgentRun, run_id)
            if run is None or run.status != "running":
                return
            try:
                run_loop(session, run, settings, provider)
            except Exception as exc:
                # Fail closed and preserve a useful trace without logging model/source payloads.
                session.rollback()
                session.refresh(run)
                code = exc.code if isinstance(exc, DomainError) else "investigation_failed"
                message = (
                    exc.message
                    if isinstance(exc, DomainError)
                    else "Investigation failed. Check service availability and retry."
                )
                if run.steps and run.steps[-1]["status"] == "running":
                    run.steps = [
                        *run.steps[:-1],
                        {
                            **run.steps[-1],
                            "status": "failed",
                            "summary": message,
                            "error_code": code,
                            "duration_ms": max(
                                0,
                                round(
                                    (
                                        datetime.now(UTC)
                                        - datetime.fromisoformat(run.steps[-1]["started_at"])
                                    ).total_seconds()
                                    * 1000
                                ),
                            ),
                        },
                    ]
                finish_run(session, run, "failed", code, message)
    except SQLAlchemyError:
        logger.error("investigation_trace_unavailable", extra={"run_id": run_id})
    finally:
        lock.release()
