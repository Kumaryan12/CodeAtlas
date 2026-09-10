"""A bounded decision/read loop. Durable trace writes are separate from repository reads."""

import json
import logging
import time
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from codeatlas.agents.tools import ReadTools
from codeatlas.agents.workspace import DraftWorkspace, workspace_digest
from codeatlas.core.errors import DomainError
from codeatlas.mcp.contracts import TOOLS as MCP_ACTIONS
from codeatlas.models.repository import AgentRun, Repository
from codeatlas.sandbox.service import agent_test
from codeatlas.schemas.agent import AgentDecision, AgentStep, DraftDecision, ExecutionDecision

MAX_TOOLS = 5
MAX_DECISIONS = 6
MAX_SECONDS = 90
MAX_CONTEXT_BYTES = 48_000
logger = logging.getLogger("codeatlas.agent")


def append_step(session, run, kind, action, transport=None):
    step = AgentStep(
        number=len(run.steps) + 1,
        transport=transport,
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
    if action == "run_tests":
        return f"{result['profile']}: {result['status']} (exit {result['exit_code']})."
    if action in ("edit_file", "create_file"):
        return f"Saved draft {result['path']}; {result['changed_files']} changed files."
    if action == "read_workspace":
        return f"Read current draft {result['path']}."
    if action == "view_diff":
        return f"Reviewed diff for {result['total']} changed files."
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
    mcp_tools = None
    if settings.read_tool_transport == "mcp":
        from codeatlas.mcp.client import MCPReadTools

        mcp_tools = MCPReadTools(tools, settings)
    workspace = DraftWorkspace(session, run, repository) if run.mode == "edit" else None
    execution = workspace is not None and run.test_profile is not None
    max_seconds = 180 if execution else MAX_SECONDS
    max_tools = 20 if execution else 10 if workspace else MAX_TOOLS
    max_decisions = max_tools + 1 if execution else 11 if workspace else MAX_DECISIONS
    decision_model = (
        ExecutionDecision if execution else DraftDecision if workspace else AgentDecision
    )
    observations = []
    started = time.monotonic()
    attempts = 0
    seen = set()
    last_test_digest = None
    for _ in range(max_decisions):
        if time.monotonic() - started >= max_seconds:
            return finish_run(
                session, run, "limited", "run_timeout", "Investigation reached its time budget."
            )
        state = {
            "task": run.task,
            "mode": run.mode,
            "test_profile": run.test_profile,
            "repository": repository.full_name,
            "commit_sha": repository.commit_sha,
            "plan": run.plan,
            "observations": observations,
            "evidence": [c.model_dump() for c in tools.evidence.values()],
            "remaining_tools": max_tools - attempts,
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
            decision = decision_model.model_validate(provider.decide(state))
        except ValidationError as exc:
            raise DomainError(
                "invalid_agent_decision", "The model proposed an invalid investigation step.", 502
            ) from exc
        if not run.plan:
            run.plan = decision.plan
        finish_step(session, run, step_started, decision.summary)
        if time.monotonic() - started >= max_seconds:
            return finish_run(
                session, run, "limited", "run_timeout", "Investigation reached its time budget."
            )
        arguments = decision.arguments.model_dump(exclude_none=True)
        if decision.action == "finish":
            if workspace and run.changes and workspace.reviewed_changes != run.changes:
                raise DomainError(
                    "diff_not_reviewed",
                    "The agent did not review its latest draft. Review the partial diff.",
                    502,
                )
            if execution and last_test_digest != workspace_digest(run):
                raise DomainError(
                    "draft_not_tested",
                    "The latest draft has no test result. Inspect its test history.",
                    502,
                )
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
        if attempts >= max_tools:
            return finish_run(
                session, run, "limited", "step_limit", "Investigation reached its tool limit."
            )
        signature = (decision.action, json.dumps(arguments, sort_keys=True))
        attempts += 1
        step_started = append_step(
            session,
            run,
            "execute"
            if decision.action == "run_tests"
            else "write"
            if decision.action in ("edit_file", "create_file")
            else "read",
            decision.action,
            "mcp" if mcp_tools and decision.action in MCP_ACTIONS else "local",
        )
        try:
            if signature in seen and decision.action not in (
                "read_workspace",
                "view_diff",
                "run_tests",
            ):
                raise DomainError(
                    "repeated_tool_call",
                    "This read was already attempted. Use its result or finish.",
                    422,
                )
            seen.add(signature)
            if execution and decision.action == "run_tests":
                if arguments:
                    raise DomainError(
                        "invalid_tool_arguments",
                        "run_tests takes no arguments; the user chooses its profile.",
                        422,
                    )
                result = agent_test(session, run, workspace, settings)
                last_test_digest = result["workspace_digest"]
            elif workspace and decision.action in (
                "read_workspace",
                "edit_file",
                "create_file",
                "view_diff",
            ):
                result = workspace.execute(decision.action, arguments)
            else:
                if mcp_tools and decision.action in MCP_ACTIONS:
                    result = mcp_tools.execute(decision.action, arguments)
                else:
                    result = tools.execute(decision.action, arguments)
        except DomainError as exc:
            result = {"error": {"code": exc.code, "message": exc.message}}
            finish_step(session, run, step_started, exc.message, exc.code)
        else:
            finish_step(
                session,
                run,
                step_started,
                ("MCP · " if mcp_tools and decision.action in MCP_ACTIONS else "")
                + tool_summary(decision.action, result),
                (result.get("error_code") or "tests_failed")
                if decision.action == "run_tests" and result["status"] != "passed"
                else None,
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
