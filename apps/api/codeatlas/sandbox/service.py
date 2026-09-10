"""Versioned, bounded test jobs shared by manual review and authorized agent tools."""

import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from codeatlas.agents.workspace import workspace_digest
from codeatlas.core.errors import DomainError
from codeatlas.models.repository import AgentRun, RepositoryFile, TestExecution
from codeatlas.sandbox.docker import require_sandbox, run_container
from codeatlas.schemas.agent import TestResponse

MAX_TEST_ATTEMPTS = 3
MAX_SOURCE_FILES = 1000
MAX_SOURCE_BYTES = 8 * 1024 * 1024


def materialize(session, run, root: Path):
    rows = session.execute(
        select(RepositoryFile.path, RepositoryFile.source)
        .where(RepositoryFile.repository_id == run.repository_id)
        .limit(MAX_SOURCE_FILES + 1)
    ).all()
    files = dict(rows)
    files.update(run.changes)
    if (
        len(files) > MAX_SOURCE_FILES
        or sum(len(s.encode()) for s in files.values()) > MAX_SOURCE_BYTES
    ):
        raise DomainError(
            "test_workspace_limit", "Tests support at most 1000 source files / 8 MiB.", 422
        )
    canonical = set()
    for path in sorted(files):
        parts = path.split("/")
        if (
            "\\" in path
            or "\x00" in path
            or any(p in ("", ".", "..") or p.lower() == ".git" for p in parts)
        ):
            raise DomainError(
                "test_workspace_path", "Snapshot contains an unsupported test path.", 422
            )
        key = path.casefold()
        if key in canonical or any(
            "/".join(parts[:i]).casefold() in canonical for i in range(1, len(parts))
        ):
            raise DomainError(
                "test_workspace_path", "Snapshot contains conflicting source paths.", 422
            )
        canonical.add(key)
    root.chmod(0o755)
    for path, source in files.items():
        target = root.joinpath(*path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.encode())
        target.chmod(0o444)
    return len(files)


def reserve_test(session, run, profile, expected_digest, image_id):
    if run.mode != "edit":
        raise DomainError("tests_not_allowed", "Tests require a draft workspace.", 422)
    if expected_digest != workspace_digest(run):
        raise DomainError(
            "stale_test_workspace", "The draft changed. Refresh its diff before testing.", 409
        )
    count = (
        session.scalar(
            select(func.count()).select_from(TestExecution).where(TestExecution.run_id == run.id)
        )
        or 0
    )
    if count >= MAX_TEST_ATTEMPTS:
        raise DomainError(
            "test_attempt_limit", "Each draft permits at most three test attempts.", 422
        )
    test = TestExecution(
        run_id=run.id, profile=profile, workspace_digest=expected_digest, image_id=image_id
    )
    session.add(test)
    session.commit()
    session.refresh(test)
    return test


def perform_test(session, run, test, settings):
    started = time.monotonic()
    try:
        if test.workspace_digest != workspace_digest(run):
            raise DomainError("stale_test_workspace", "Draft changed before testing.", 409)
        settings.workspace_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="tests-", dir=settings.workspace_root) as directory:
            root = Path(directory).resolve()
            materialize(session, run, root)
            result = run_container(root, test.profile, test.image_id)
        test.status, test.exit_code = result.status, result.exit_code
        test.stdout, test.stderr, test.error_code = result.stdout, result.stderr, result.error_code
    except Exception as exc:
        test.status = "error"
        test.error_code = exc.code if isinstance(exc, DomainError) else "sandbox_failed"
    test.duration_ms = round((time.monotonic() - started) * 1000)
    test.finished_at = datetime.now(UTC)
    session.commit()
    return TestResponse.model_validate(test, from_attributes=True)


def execute_manual_test(engine, test_id, settings, lock):
    try:
        with Session(engine, expire_on_commit=False) as session:
            test = session.get(TestExecution, test_id)
            if test is not None and test.status == "running":
                perform_test(session, session.get(AgentRun, test.run_id), test, settings)
    finally:
        lock.release()


def agent_test(session, run, workspace, settings):
    if not run.test_profile:
        raise DomainError("tests_not_allowed", "This run has no test execution permission.", 422)
    if workspace.reviewed_changes != run.changes:
        raise DomainError(
            "diff_not_reviewed", "Review the latest diff before executing tests.", 422
        )
    image = require_sandbox(settings, run.test_profile)
    test = reserve_test(session, run, run.test_profile, workspace_digest(run), image)
    result = perform_test(session, run, test, settings).model_dump(mode="json")
    # Full bounded output is durable; send only a small excerpt back to the model.
    result["stdout"] = result["stdout"][:3000]
    result["stderr"] = result["stderr"][:3000]
    result["output_note"] = (
        "Output excerpts may be shortened; full bounded output is in test history."
    )
    return result
