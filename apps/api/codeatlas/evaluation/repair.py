"""Opt-in live Claude repair demo with real Docker tests and immutable source checks."""

import argparse
import hashlib
import json
import tempfile
import threading
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from codeatlas.agents.runner import execute_run
from codeatlas.agents.workspace import unified_diff, workspace_digest
from codeatlas.ai.investigator import EXECUTION_INSTRUCTIONS, get_investigator
from codeatlas.ai.usage import summarize_usage
from codeatlas.core.config import Settings
from codeatlas.core.errors import DomainError
from codeatlas.models.repository import (
    AgentRun,
    Base,
    CodeSymbol,
    Repository,
    RepositoryFile,
    TestExecution,
)
from codeatlas.parsers.python import parse_python
from codeatlas.sandbox.docker import require_sandbox, run_container

SOURCE = """def normalize_email(email):
    if not email or "@" not in email:
        raise ValueError("Invalid email")
    return email.strip()
"""
TESTS = """import unittest
from auth import normalize_email

class NormalizeTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize_email("  USER@EXAMPLE.COM  "), "user@example.com")
        self.assertEqual(normalize_email("a@b.com"), "a@b.com")

    def test_invalid(self):
        for value in ["", "invalid", None]:
            with self.assertRaises(ValueError):
                normalize_email(value)
"""
TASK = (
    "Fix normalize_email in auth.py so it strips whitespace AND lowercases email addresses, "
    "while retaining its existing invalid-input behavior. Inspect the source and test_auth.py. "
    "Change only auth.py; do not change or add tests. Review the diff and run the authorized "
    "python-unittest profile. Finish with a cited explanation "
    "of the change and observed test result."
)


def check_container(root, source, image):
    root.mkdir()
    root.chmod(0o755)
    (root / "auth.py").write_text(source)
    (root / "test_auth.py").write_text(TESTS)
    return run_container(root, "python-unittest", image)


def evaluate(output):
    settings = Settings()
    image = require_sandbox(settings, "python-unittest")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="codeatlas-repair-") as directory:
        root = Path(directory)
        # Docker's non-root user must traverse the parent too.
        root.chmod(0o755)
        config = settings.model_copy(
            update={"read_tool_transport": "mcp", "workspace_root": root / "work"}
        )
        config.database_url = type(settings.database_url)(f"sqlite:///{root / 'demo.sqlite'}")
        engine = create_engine(config.database_url.get_secret_value())
        Base.metadata.create_all(engine)
        baseline = check_container(root / "baseline", SOURCE, image)
        with Session(engine) as session:
            repo = Repository(
                url="https://example.invalid/repair-demo",
                full_name="fixture/repair",
                status="ready",
                commit_sha=hashlib.sha1(SOURCE.encode()).hexdigest(),
            )
            session.add(repo)
            session.flush()
            for path, source in {"auth.py": SOURCE, "test_auth.py": TESTS}.items():
                parsed = parse_python(source)
                file = RepositoryFile(
                    repository_id=repo.id,
                    path=path,
                    language="python",
                    size_bytes=len(source.encode()),
                    source=source,
                    symbol_count=len(parsed.symbols),
                    imports=parsed.imports,
                    import_references=[r.model_dump() for r in parsed.import_references],
                )
                session.add(file)
                session.flush()
                for symbol in parsed.symbols:
                    session.add(CodeSymbol(file_id=file.id, **symbol.model_dump()))
            run = AgentRun(
                repository_id=repo.id,
                mode="edit",
                test_profile="python-unittest",
                task=TASK,
                model=config.reasoning_model,
            )
            session.add(run)
            session.commit()
            run_id = run.id
        lock = threading.Lock()
        lock.acquire()
        execute_run(engine, run_id, config, get_investigator(config), lock)
        with Session(engine) as session:
            run = session.get(AgentRun, run_id)
            original = dict(
                session.execute(
                    select(RepositoryFile.path, RepositoryFile.source).where(
                        RepositoryFile.repository_id == run.repository_id
                    )
                ).all()
            )
            changed = run.changes.get("auth.py", SOURCE)
            # Independently rerun the original tests, never an agent-modified test file.
            validation = check_container(root / "validation", changed, image)
            executions = [
                {
                    "status": t.status,
                    "workspace_digest": t.workspace_digest,
                    "stdout": t.stdout,
                    "stderr": t.stderr,
                    "error_code": t.error_code,
                }
                for t in session.scalars(
                    select(TestExecution).where(TestExecution.run_id == run_id)
                )
            ]
            checks = {
                "baseline_failed": baseline.status == "failed" and baseline.exit_code == 1,
                "run_completed": run.status == "completed",
                "only_auth_changed": set(run.changes) == {"auth.py"},
                "snapshot_unchanged": original == {"auth.py": SOURCE, "test_auth.py": TESTS},
                "independent_tests_passed": validation.status == "passed",
                "agent_tested_final_draft": any(
                    t["status"] == "passed" and t["workspace_digest"] == workspace_digest(run)
                    for t in executions
                ),
            }
            report = {
                "version": "repair-v1",
                "created_at": datetime.now(UTC).isoformat(),
                "model": config.reasoning_model,
                "transport": config.read_tool_transport,
                "fixture_sha256": hashlib.sha256((SOURCE + TESTS).encode()).hexdigest(),
                "task": TASK,
                "task_sha256": hashlib.sha256(TASK.encode()).hexdigest(),
                "prompt_sha256": hashlib.sha256(EXECUTION_INSTRUCTIONS.encode()).hexdigest(),
                "baseline": asdict(baseline),
                "validation": asdict(validation),
                "status": run.status,
                "error_code": run.error_code,
                "checks": checks,
                "passed": all(checks.values()),
                "steps": run.steps,
                "result": run.result,
                "usage": summarize_usage(run.steps),
                "test_executions": executions,
                "patch": unified_diff("auth.py", SOURCE, changed),
                "duration_ms": round((time.monotonic() - started) * 1000),
                "limitations": [
                    "One authored synthetic bug; not real-repository repair accuracy.",
                    "No patch is applied to a user's repository or pushed upstream.",
                    "Final explanation citation entailment is not automatically graded.",
                ],
            }
        engine.dispose()
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = evaluate(args.output)
    except DomainError as exc:
        parser.exit(2, f"{exc.code}: {exc.message}\n")
    print(
        json.dumps(
            {"passed": report["passed"], "checks": report["checks"], "error": report["error_code"]}
        )
    )

    parser.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
