import json
import subprocess

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_agent import ScriptedInvestigator
from test_qa import imported, mock_http

from codeatlas.agents.workspace import DraftWorkspace, digest, unified_diff
from codeatlas.ai.investigator import OpenAIInvestigator
from codeatlas.api.agent import investigator_dependency, recover_interrupted
from codeatlas.core.config import Settings
from codeatlas.core.errors import DomainError
from codeatlas.models.repository import AgentRun, Repository, RepositoryFile
from codeatlas.schemas.agent import DraftDecision


def decision(action, arguments=None):
    return DraftDecision(
        plan=["Inspect source", "Propose edit", "Review diff"],
        summary=action,
        action=action,
        arguments=arguments or {},
        answer={"status": "insufficient_context", "claims": []} if action == "finish" else None,
    )


@pytest.fixture
def workspace(api, fake_download):
    prefix = imported(api)
    with Session(api.app.state.database) as session:
        repository = session.get(Repository, prefix.rsplit("/", 1)[1])
        run = AgentRun(repository_id=repository.id, mode="edit", model="fixture", task="Edit login")
        session.add(run)
        session.commit()
        yield DraftWorkspace(session, run, repository)


def test_edits_are_isolated_stale_safe_and_reversible(workspace):
    w = workspace
    original = w.original("auth.py")
    read = w.execute("read_workspace", {"path": "auth.py"})
    args = {
        "path": "auth.py",
        "expected_sha256": read["sha256"],
        "old_text": "return email",
        "new_text": "return email.strip()",
    }
    w.execute("edit_file", args)
    assert w.original("auth.py") == original
    assert "+" in w.diff().files[0].diff
    with pytest.raises(DomainError) as exc:
        w.execute("edit_file", args)
    assert exc.value.code == "stale_workspace_read"
    other = AgentRun(
        repository_id=w.repository.id, mode="edit", task="Other", model="fixture", changes={}
    )
    assert DraftWorkspace(w.session, other, w.repository).current("auth.py") == original
    read = w.execute("read_workspace", {"path": "auth.py"})
    w.execute(
        "edit_file",
        {
            **args,
            "expected_sha256": read["sha256"],
            "old_text": "return email.strip()",
            "new_text": "return email",
        },
    )
    assert not w.run.changes and w.diff().total == 0


@pytest.mark.parametrize(
    "path",
    [
        "../escape.py",
        "/abs.py",
        "a//b.py",
        "a/./b.py",
        ".git/config.py",
        "a/.GIT/hook.py",
        "a\\b.py",
        "a\nb.py",
        "x.ts/../b.py",
        "file.sh",
        "a\x00.py",
        "https://x.py",
    ],
)
def test_invalid_paths_cannot_create_drafts(workspace, path):
    with pytest.raises(DomainError):
        workspace.execute("create_file", {"path": path, "content": "pass"})
    assert not workspace.run.changes


def test_create_collisions_and_size_limits(workspace):
    w = workspace
    for path in ["auth.py", "AUTH.py", "auth.py/child.py"]:
        with pytest.raises(DomainError):
            w.execute("create_file", {"path": path, "content": "pass"})
    for source in ["é" * 6001, "\x00"]:
        with pytest.raises(DomainError):
            w.execute("create_file", {"path": "new.py", "content": source})
    for i in range(5):
        w.execute("create_file", {"path": f"new{i}.py", "content": "x" * 12000})
    with pytest.raises(DomainError) as exc:
        w.execute("create_file", {"path": "more.py", "content": "x"})
    assert exc.value.code == "workspace_limit" and len(w.run.changes) == 5
    for i in range(5, 10):
        w.execute("create_file", {"path": f"new{i}.py", "content": ""})
    with pytest.raises(DomainError):
        w.execute("create_file", {"path": "empty.py", "content": ""})


def test_edit_requires_read_and_unique_match(workspace):
    original = workspace.original("auth.py")
    args = {
        "path": "auth.py",
        "expected_sha256": digest(original),
        "old_text": "email",
        "new_text": "x",
    }
    with pytest.raises(DomainError) as exc:
        workspace.execute("edit_file", args)
    assert exc.value.code == "stale_workspace_read"
    workspace.execute("read_workspace", {"path": "auth.py"})
    with pytest.raises(DomainError) as exc:
        workspace.execute("edit_file", args)
    assert exc.value.code == "ambiguous_edit"
    with pytest.raises(DomainError):
        workspace.execute("create_file", {"path": "new.py", "content": "pass", "command": None})
    workspace.run.mode = "investigate"
    with pytest.raises(DomainError):
        workspace.execute("create_file", {"path": "new.py", "content": "pass"})


@pytest.mark.parametrize(
    "before,after",
    [
        ("x=1", "x=2"),
        ("x=1\r\n", "x=2\r\n"),
        ("s='a\u2028b'\n", "s='a\u2028c'\n"),
        (None, "pass\n"),
        (None, ""),
        ("pass\n", ""),
    ],
)
def test_diff_applies_exact_bytes_in_disposable_directory(tmp_path, before, after):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    path = tmp_path / "example.py"
    if before is not None:
        path.write_bytes(before.encode())
    patch = unified_diff("example.py", before, after)
    applied = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        cwd=tmp_path,
        input=patch.encode(),
        capture_output=True,
    )
    assert applied.returncode == 0, applied.stderr.decode()
    assert path.read_bytes() == after.encode()


def test_edit_run_persists_diff_and_recovers_after_failure(api, fake_download):
    prefix = imported(api)
    original_files = api.get(prefix + "/files").json()
    provider = ScriptedInvestigator(
        [
            decision("read_workspace", {"path": "auth.py"}),
            lambda state: decision(
                "edit_file",
                {
                    "path": "auth.py",
                    "expected_sha256": state["observations"][-1]["result"]["sha256"],
                    "old_text": "return email",
                    "new_text": "return email.strip()",
                },
            ),
            decision(
                "create_file",
                {"path": "test_login.py", "content": "def test_login():\n    assert True\n"},
            ),
            decision("view_diff"),
            RuntimeError("private-model-secret"),
        ]
    )
    api.app.dependency_overrides[investigator_dependency] = lambda: provider
    started = api.post(prefix + "/agent-runs", json={"task": "Trim login input", "mode": "edit"})
    assert started.status_code == 202, started.text
    url = prefix + "/agent-runs/" + started.json()["id"]
    run = api.get(url).json()
    assert run["status"] == "failed" and run["mode"] == "edit"
    assert len([s for s in run["steps"] if s["kind"] == "write"]) == 2
    diff = api.get(url + "/diff").json()
    assert diff["total"] == 2 and "+        return email.strip()" in diff["files"][0]["diff"]
    assert "private-model-secret" not in json.dumps(run)
    assert api.get(prefix + "/files").json() == original_files
    with Session(api.app.state.database) as session:
        stored = session.get(AgentRun, run["id"])
        stored.status = "running"
        session.commit()
    recover_interrupted(api.app.state.database)
    assert api.get(url).json()["status"] == "interrupted"
    assert api.get(url + "/diff").json() == diff
    other = imported(api)
    assert api.get(other + "/agent-runs/" + run["id"] + "/diff").status_code == 404
    assert api.post(url + "/diff", json={}).status_code == 405
    with Session(api.app.state.database) as session:
        assert "strip()" not in session.scalar(
            select(RepositoryFile.source).where(
                RepositoryFile.repository_id == run["repository_id"],
                RepositoryFile.path == "auth.py",
            )
        )


def test_edit_provider_only_exposes_writes_in_explicit_mode(monkeypatch):
    def handler(request):
        payload = json.loads(request.content)
        assert "tools" not in payload and payload["store"] is False
        schema = payload["text"]["format"]["schema"]
        assert "edit_file" in schema["properties"]["action"]["enum"]
        assert "expected_sha256" in schema["properties"]["arguments"]["required"]
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": decision("finish").model_dump_json()}
                        ],
                    }
                ],
            },
        )

    mock_http(monkeypatch, handler)
    assert (
        OpenAIInvestigator(Settings(_env_file=None, openai_api_key="test"))
        .decide({"mode": "edit"})
        .action
        == "finish"
    )


@pytest.mark.parametrize("review", [True, False])
def test_completed_draft_requires_review_of_latest_changes(api, fake_download, review):
    prefix = imported(api)
    choices = [decision("create_file", {"path": "new.py", "content": "pass\n"})]
    if review:
        choices.append(decision("view_diff"))
    choices.append(decision("finish"))
    api.app.dependency_overrides[investigator_dependency] = lambda: ScriptedInvestigator(choices)
    response = api.post(prefix + "/agent-runs", json={"task": "Create a stub", "mode": "edit"})
    run = api.get(prefix + "/agent-runs/" + response.json()["id"]).json()
    assert run["status"] == ("completed" if review else "failed")
    assert run["error_code"] == (None if review else "diff_not_reviewed")
