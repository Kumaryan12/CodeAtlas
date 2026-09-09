import json

import httpx
import pytest
from sqlalchemy.orm import Session
from test_qa import imported, mock_http

from codeatlas.agents.tools import ReadTools
from codeatlas.ai.investigator import OpenAIInvestigator
from codeatlas.api.agent import investigator_dependency, recover_interrupted
from codeatlas.core.config import Settings
from codeatlas.core.errors import DomainError
from codeatlas.models.repository import AgentRun, Repository
from codeatlas.schemas.agent import AgentDecision


def decision(action, arguments=None, answer=None):
    return AgentDecision(
        plan=["Find relevant files", "Inspect implementation", "Summarize evidence"],
        summary=f"Next action: {action}",
        action=action,
        arguments=arguments or {},
        answer=answer,
    )


class ScriptedInvestigator:
    def __init__(self, decisions):
        self.decisions = iter(decisions)
        self.states = []

    def decide(self, state):
        self.states.append(state)
        value = next(self.decisions)
        if isinstance(value, Exception):
            raise value
        return value(state) if callable(value) else value

    def embed(self, texts):
        return [[1, 0] for _ in texts]


def start(api, prefix, provider):
    api.app.dependency_overrides[investigator_dependency] = lambda: provider
    response = api.post(prefix + "/agent-runs", json={"task": "Investigate login"})
    assert response.status_code == 202, response.text
    result = api.get(prefix + "/agent-runs/" + response.json()["id"])
    assert result.status_code == 200, result.text
    return result.json()


def test_investigation_executes_reads_and_persists_cited_trace(api, fake_download):
    prefix = imported(api)

    def read_auth(state):
        file = next(
            row for row in state["observations"][-1]["result"]["files"] if row["path"] == "auth.py"
        )
        return decision("read_file", {"file_id": file["file_id"], "start_line": 2, "end_line": 3})

    provider = ScriptedInvestigator(
        [
            decision("list_files"),
            read_auth,
            decision(
                "finish",
                answer={
                    "status": "answered",
                    "claims": [{"text": "Login returns the email.", "citation_ids": ["E1"]}],
                },
            ),
        ]
    )
    result = start(api, prefix, provider)
    assert result["status"] == "completed", result
    assert [step["kind"] for step in result["steps"]] == ["model", "read", "model", "read", "model"]
    assert all(step["status"] == "completed" for step in result["steps"])
    citation = result["result"]["citations"][0]
    assert (citation["start_line"], citation["end_line"]) == (2, 3)
    assert "return email" in citation["source"]
    with Session(api.app.state.database) as session:
        stored = session.get(AgentRun, result["id"])
        assert "source" not in stored.result["citations"][0]
        assert "return email" not in json.dumps(stored.steps)
    history = api.get(prefix + "/agent-runs").json()
    assert history["total"] == 1 and "steps" not in history["items"][0]
    other = imported(api)
    assert api.get(other + "/agent-runs/" + result["id"]).status_code == 404
    assert api.app.state.ai_lock.acquire(blocking=False)
    api.app.state.ai_lock.release()


@pytest.mark.parametrize("action", ["run_shell", "edit_file", "open_url", "delete_repository"])
def test_unregistered_model_actions_fail_without_execution(api, fake_download, action):
    prefix = imported(api)
    provider = ScriptedInvestigator(
        [
            {
                "plan": ["Unsafe"],
                "summary": "Attempt action",
                "action": action,
                "arguments": {},
                "answer": None,
            }
        ]
    )
    result = start(api, prefix, provider)
    assert result["status"] == "failed"
    assert result["error_code"] == "invalid_agent_decision"
    assert all(step["kind"] == "model" for step in result["steps"])
    assert api.get(prefix + "/files").json()["total"] == 3


def test_fabricated_evidence_is_rejected(api, fake_download):
    prefix = imported(api)
    provider = ScriptedInvestigator(
        [
            decision(
                "finish",
                answer={
                    "status": "answered",
                    "claims": [{"text": "Unsupported", "citation_ids": ["E999"]}],
                },
            )
        ]
    )
    result = start(api, prefix, provider)
    assert result["status"] == "failed" and result["error_code"] == "invalid_citations"
    assert result["result"] is None


def test_tool_budget_and_repeated_reads_are_bounded(api, fake_download):
    prefix = imported(api)
    provider = ScriptedInvestigator([decision("list_files")] * 6)
    result = start(api, prefix, provider)
    assert result["status"] == "limited" and result["error_code"] == "step_limit"
    assert len(result["steps"]) == 11
    assert sum(step["error_code"] == "repeated_tool_call" for step in result["steps"]) == 4


def test_invalid_tool_range_and_foreign_id_are_observations(api, fake_download):
    prefix, other = imported(api), imported(api)
    foreign = api.get(other + "/files").json()["items"][0]["id"]
    provider = ScriptedInvestigator(
        [
            decision("read_file", {"file_id": foreign, "start_line": 1, "end_line": 1}),
            decision("read_file", {"file_id": foreign, "start_line": 1, "end_line": 121}),
            decision("finish", answer={"status": "insufficient_context", "claims": []}),
        ]
    )
    result = start(api, prefix, provider)
    assert result["status"] == "completed"
    assert result["result"]["status"] == "insufficient_context"
    assert [row["error_code"] for row in result["steps"] if row["kind"] == "read"] == [
        "file_not_found",
        "invalid_tool_arguments",
    ]
    assert not provider.states[-1]["evidence"]


def test_provider_failure_preserves_failed_step_without_secret_payload(api, fake_download):
    prefix = imported(api)
    result = start(api, prefix, ScriptedInvestigator([RuntimeError("private-source-secret")]))
    assert result["status"] == "failed"
    assert result["steps"][-1]["status"] == "failed"
    assert "private-source-secret" not in json.dumps(result)


def test_time_and_context_limits_stop_before_a_model_call(api, fake_download, monkeypatch):
    prefix = imported(api)
    provider = ScriptedInvestigator([])
    monkeypatch.setattr("codeatlas.agents.runner.MAX_SECONDS", 0)
    result = start(api, prefix, provider)
    assert result["error_code"] == "run_timeout" and not provider.states
    monkeypatch.setattr("codeatlas.agents.runner.MAX_SECONDS", 90)
    monkeypatch.setattr("codeatlas.agents.runner.MAX_CONTEXT_BYTES", 1)
    result = start(api, prefix, provider)
    assert result["error_code"] == "context_limit" and not provider.states


def test_busy_validation_and_missing_configuration(api, fake_download):
    prefix = imported(api)
    assert api.post(prefix + "/agent-runs", json={"task": "Investigate"}).status_code == 503
    api.app.dependency_overrides[investigator_dependency] = lambda: ScriptedInvestigator([])
    assert api.post(prefix + "/agent-runs", json={"task": " "}).status_code == 422
    assert api.post(prefix + "/agent-runs", content=b"x" * 4097).status_code == 413
    api.app.state.ai_lock.acquire()
    try:
        assert api.post(prefix + "/agent-runs", json={"task": "Investigate"}).status_code == 409
    finally:
        api.app.state.ai_lock.release()


def test_restart_marks_unfinished_run_interrupted(api, fake_download):
    prefix = imported(api)
    with Session(api.app.state.database) as session:
        run = AgentRun(repository_id=prefix.rsplit("/", 1)[1], task="Earlier task", model="fixture")
        session.add(run)
        session.commit()
        run_id = run.id
    recover_interrupted(api.app.state.database)
    result = api.get(prefix + "/agent-runs/" + run_id).json()
    assert result["status"] == "interrupted" and result["error_code"] == "server_restarted"


def test_read_registry_rejects_mutations_and_argument_injection(api, fake_download):
    prefix = imported(api)
    with Session(api.app.state.database) as session:
        tools = ReadTools(
            session, session.get(Repository, prefix.rsplit("/", 1)[1]), api.app.state.settings, None
        )
        for action in ["write_file", "shell", "http_get"]:
            with pytest.raises(DomainError, match="registered"):
                tools.execute(action, {})
        with pytest.raises(DomainError):
            tools.execute("list_files", {"command": "rm -rf /"})
        with pytest.raises(DomainError):
            tools.execute(
                "read_file", {"file_id": "../../etc/passwd", "start_line": 1, "end_line": 2}
            )
        assert tools.execute("list_files", {"prefix": "../"})["files"] == []


def test_provider_decision_wire_format_has_no_hosted_execution_tools(monkeypatch):
    def handler(request):
        payload = json.loads(request.content)
        assert payload["store"] is False and "tools" not in payload
        assert "untrusted" in payload["instructions"]
        assert payload["text"]["format"]["strict"] is True
        data = decision(
            "finish", answer={"status": "insufficient_context", "claims": []}
        ).model_dump_json()
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": data}]}],
            },
        )

    mock_http(monkeypatch, handler)
    provider = OpenAIInvestigator(Settings(_env_file=None, openai_api_key="test"))
    assert provider.decide({"task": "inspect"}).action == "finish"
