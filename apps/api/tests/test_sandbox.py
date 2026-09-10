import json
import subprocess

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_agent import ScriptedInvestigator, start
from test_qa import imported
from test_workspace import decision as draft_decision

from codeatlas.agents.workspace import workspace_digest
from codeatlas.api.agent import investigator_dependency, recover_interrupted
from codeatlas.core.errors import DomainError
from codeatlas.models.repository import AgentRun
from codeatlas.models.repository import TestExecution as Execution
from codeatlas.sandbox import docker, service
from codeatlas.sandbox.docker import Outcome
from codeatlas.schemas.agent import ExecutionDecision

IMAGE = "sha256:" + "a" * 64


def decision(action, arguments=None):
    return ExecutionDecision(
        plan=["Inspect", "Patch", "Review and test"],
        summary=action,
        action=action,
        arguments=arguments or {},
        answer={"status": "insufficient_context", "claims": []} if action == "finish" else None,
    )


@pytest.fixture
def enabled(api, monkeypatch):
    api.app.state.settings.sandbox_enabled = True
    monkeypatch.setattr(
        docker,
        "docker_command",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, (IMAGE + "\n").encode(), b""),
    )
    return api


def test_container_command_is_fixed_and_has_resource_boundaries(tmp_path):
    args = docker.create_arguments("codeatlas-test-fixed", tmp_path, "python-unittest", IMAGE)
    for flag in [
        "--network=none",
        "--read-only",
        "--user=65534:65534",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--memory=256m",
        "--memory-swap=256m",
        "--cpus=1",
        "--pids-limit=64",
        "--log-driver=none",
        "--pull=never",
    ]:
        assert flag in args
    assert args.count("--mount") == 1
    assert args[args.index("--mount") + 1].endswith("dst=/workspace,readonly")
    assert args[args.index(IMAGE) + 1 :] == [
        "--signal=KILL",
        "30s",
        "python",
        "-I",
        "-B",
        "/opt/codeatlas/unittest_runner.py",
    ]
    assert not any(
        "docker.sock" in value or "--privileged" in value or "--env-file" in value for value in args
    )
    assert docker.clean_output(b"\x1b[31mred\x1b[0m\x00\r\n") == "red\n"


def test_manual_execution_is_versioned_scoped_and_bounded(enabled, fake_download, monkeypatch):
    api = enabled
    prefix = imported(api)
    run = start(api, prefix, ScriptedInvestigator([draft_decision("finish")]))
    with Session(api.app.state.database) as session:
        stored = session.get(AgentRun, run["id"])
        stored.mode = "edit"
        stored.changes = {"test_login.py": "import unittest\n"}
        session.commit()
    url = prefix + "/agent-runs/" + run["id"]
    diff = api.get(url + "/diff").json()
    payload = {"profile": "python-unittest", "workspace_digest": diff["workspace_digest"]}
    seen = []

    def execute(root, profile, image):
        assert (root / "auth.py").exists() and (root / "test_login.py").exists()
        assert not (root / ".env").exists()
        seen.append(root)
        return Outcome("failed", 1, stdout="test output", stderr="assertion failed")

    monkeypatch.setattr(service, "run_container", execute)
    assert (
        api.post(url + "/test-runs", json={**payload, "workspace_digest": "0" * 64}).status_code
        == 409
    )
    for _ in range(3):
        response = api.post(url + "/test-runs", json=payload)
        assert response.status_code == 202, response.text
        assert response.json()["status"] == "running"
    assert (
        api.post(url + "/test-runs", json=payload).json()["error"]["code"] == "test_attempt_limit"
    )
    rows = api.get(url + "/test-runs").json()
    assert len(rows) == 3 and all(row["status"] == "failed" for row in rows)
    assert rows[0]["exit_code"] == 1 and rows[0]["stderr"] == "assertion failed"
    assert (
        rows[0]["workspace_digest"] == payload["workspace_digest"] and rows[0]["image_id"] == IMAGE
    )
    assert all(not root.exists() for root in seen)
    other = imported(api)
    assert api.get(other + "/agent-runs/" + run["id"] + "/test-runs").status_code == 404
    assert (
        api.post(url + "/test-runs", json={**payload, "command": "echo unsafe"}).status_code == 422
    )
    assert api.post(url + "/test-runs", json={**payload, "profile": "shell"}).status_code == 422


def test_execution_permissions_and_busy_guards(api, fake_download, monkeypatch):
    prefix = imported(api)
    api.app.dependency_overrides[investigator_dependency] = lambda: ScriptedInvestigator([])
    payload = {"task": "Test", "mode": "edit", "test_profile": "python-unittest"}
    assert (
        api.post(prefix + "/agent-runs", json=payload).json()["error"]["code"] == "sandbox_disabled"
    )
    assert (
        api.post(prefix + "/agent-runs", json={**payload, "mode": "investigate"}).status_code == 422
    )
    run = start(
        api,
        prefix,
        ScriptedInvestigator(
            [
                {
                    "plan": ["Test"],
                    "summary": "Test",
                    "action": "run_tests",
                    "arguments": {},
                    "answer": None,
                }
            ]
        ),
    )
    assert run["error_code"] == "invalid_agent_decision"
    with Session(api.app.state.database) as session:
        stored = session.get(AgentRun, run["id"])
        stored.mode = "edit"
        stored.status = "running"
        session.commit()
        digest = workspace_digest(stored)
    url = prefix + "/agent-runs/" + run["id"] + "/test-runs"
    assert (
        api.post(url, json={"profile": "python-unittest", "workspace_digest": digest}).status_code
        == 409
    )
    with Session(api.app.state.database) as session:
        stored = session.get(AgentRun, run["id"])
        stored.status = "failed"
        session.commit()
    api.app.state.ai_lock.acquire()
    try:
        assert (
            api.post(
                url, json={"profile": "python-unittest", "workspace_digest": digest}
            ).status_code
            == 409
        )
    finally:
        api.app.state.ai_lock.release()


def test_agent_repairs_failure_and_retests_latest_draft(enabled, fake_download, monkeypatch):
    api = enabled
    prefix = imported(api)
    attempts = []

    def execute(root, profile, image):
        value = (root / "new.py").read_text()
        attempts.append(value)
        return Outcome(
            "failed" if value == "x = 1\n" else "passed",
            1 if value == "x = 1\n" else 0,
            stderr="expected 2" if value == "x = 1\n" else "",
        )

    monkeypatch.setattr(service, "run_container", execute)
    choices = [
        decision("create_file", {"path": "new.py", "content": "x = 1\n"}),
        decision("view_diff"),
        decision("run_tests"),
        decision("read_workspace", {"path": "new.py"}),
        lambda state: decision(
            "edit_file",
            {
                "path": "new.py",
                "expected_sha256": state["observations"][-1]["result"]["sha256"],
                "old_text": "x = 1",
                "new_text": "x = 2",
            },
        ),
        decision("view_diff"),
        decision("run_tests"),
        decision("finish"),
    ]
    provider = ScriptedInvestigator(choices)
    api.app.dependency_overrides[investigator_dependency] = lambda: provider
    response = api.post(
        prefix + "/agent-runs",
        json={"task": "Fix", "mode": "edit", "test_profile": "python-unittest"},
    )
    assert response.status_code == 202
    url = prefix + "/agent-runs/" + response.json()["id"]
    run = api.get(url).json()
    assert run["status"] == "completed", run
    assert attempts == ["x = 1\n", "x = 2\n"]
    assert [step["status"] for step in run["steps"] if step["kind"] == "execute"] == [
        "failed",
        "completed",
    ]
    tests = api.get(url + "/test-runs").json()
    assert [test["status"] for test in tests] == ["failed", "passed"]
    assert tests[0]["workspace_digest"] != tests[1]["workspace_digest"]
    assert tests[1]["workspace_digest"] == api.get(url + "/diff").json()["workspace_digest"]
    assert "expected 2" in json.dumps(provider.states)
    assert "expected 2" not in json.dumps(run["steps"])


def test_agent_attempt_limit_and_unreviewed_execution(enabled, fake_download, monkeypatch):
    api = enabled
    prefix = imported(api)
    calls = []
    monkeypatch.setattr(
        service, "run_container", lambda *args: calls.append(1) or Outcome("failed", 1)
    )
    provider = ScriptedInvestigator(
        [
            decision("run_tests"),
            decision("view_diff"),
            *[decision("run_tests") for _ in range(4)],
            decision("finish"),
        ]
    )
    api.app.dependency_overrides[investigator_dependency] = lambda: provider
    response = api.post(
        prefix + "/agent-runs",
        json={"task": "Test", "mode": "edit", "test_profile": "python-unittest"},
    )
    run = api.get(prefix + "/agent-runs/" + response.json()["id"]).json()
    assert run["status"] == "completed" and len(calls) == 3
    assert run["steps"][1]["error_code"] == "diff_not_reviewed"
    assert any(step["error_code"] == "test_attempt_limit" for step in run["steps"])


def test_materialization_rejects_traversal_and_size(api, fake_download, tmp_path, monkeypatch):
    prefix = imported(api)
    with Session(api.app.state.database) as session:
        run = AgentRun(
            repository_id=prefix.rsplit("/", 1)[1],
            mode="edit",
            model="fixture",
            task="Test",
            changes={"../escape.py": "bad"},
        )
        session.add(run)
        session.flush()
        with pytest.raises(DomainError) as exc:
            service.materialize(session, run, tmp_path / "sources")
        assert exc.value.code == "test_workspace_path"
        assert not (tmp_path / "escape.py").exists()
        run.changes = {}
        monkeypatch.setattr(service, "MAX_SOURCE_BYTES", 1)
        with pytest.raises(DomainError) as exc:
            service.materialize(session, run, tmp_path / "sources")
        assert exc.value.code == "test_workspace_limit"


def test_restart_preserves_completed_tests_and_marks_pending_interrupted(api, fake_download):
    prefix = imported(api)
    with Session(api.app.state.database) as session:
        run = AgentRun(
            repository_id=prefix.rsplit("/", 1)[1], mode="edit", model="fixture", task="Test"
        )
        session.add(run)
        session.flush()
        session.add_all(
            [
                Execution(run_id=run.id, profile="node-test", workspace_digest="a" * 64),
                Execution(
                    run_id=run.id,
                    profile="node-test",
                    workspace_digest="a" * 64,
                    status="passed",
                    exit_code=0,
                ),
            ]
        )
        session.commit()
        run_id = run.id
    recover_interrupted(api.app.state.database)
    with Session(api.app.state.database) as session:
        results = list(session.scalars(select(Execution).where(Execution.run_id == run_id)))
        assert {row.status for row in results} == {"interrupted", "passed"}
        assert (
            next(row for row in results if row.status == "interrupted").error_code
            == "server_restarted"
        )
