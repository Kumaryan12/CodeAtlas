import json

import httpx
import pytest
from pydantic import ValidationError
from test_qa import imported, mock_http

from codeatlas.ai.anthropic import AnthropicInvestigator, AnthropicProvider
from codeatlas.ai.investigator import get_investigator
from codeatlas.ai.provider import OpenAIProvider, get_provider
from codeatlas.core.config import Settings
from codeatlas.core.errors import DomainError


def settings(**kwargs):
    return Settings(_env_file=None, anthropic_api_key="claude-test-secret", **kwargs)


def completed(value):
    return {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(value)}]}


def test_provider_selection_and_independent_keys():
    config = settings()
    assert isinstance(get_provider(config), AnthropicProvider)
    assert isinstance(get_investigator(config), AnthropicInvestigator)
    assert config.reasoning_model == "claude-sonnet-5"
    with pytest.raises(DomainError, match="CODEATLAS_OPENAI_API_KEY"):
        get_provider(config).embed(["code"])
    openai = Settings(_env_file=None, reasoning_provider="openai", openai_api_key="fixture")
    assert isinstance(get_provider(openai), OpenAIProvider)
    assert openai.reasoning_model == "gpt-4.1-mini"
    assert settings(answer_model="claude-sonnet-4-6").reasoning_model == "claude-sonnet-4-6"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, reasoning_provider="unknown")
    # Having the embedding key must not silently select a different reasoning provider.
    with pytest.raises(DomainError, match="CODEATLAS_ANTHROPIC_API_KEY"):
        get_investigator(Settings(_env_file=None, openai_api_key="fixture"))


def test_claude_answer_and_embeddings_use_separate_hosts_and_credentials(monkeypatch):
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        payload = json.loads(request.content)
        if request.url.host == "api.openai.com":
            assert request.headers["authorization"] == "Bearer embedding-test-secret"
            assert "x-api-key" not in request.headers
            assert payload["model"] == "text-embedding-3-small"
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 0]}]})
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == "claude-test-secret"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert "authorization" not in request.headers
        assert payload["model"] == "claude-sonnet-5"
        assert payload["max_tokens"] == 2000
        assert payload["output_config"]["format"]["type"] == "json_schema"
        assert "untrusted" in payload["system"]
        assert json.loads(payload["messages"][0]["content"])["excerpts"] == [{"source": "code"}]
        assert "tools" not in payload and "store" not in payload
        return httpx.Response(200, json=completed({"status": "insufficient_context", "claims": []}))

    mock_http(monkeypatch, handler)
    provider = get_provider(settings(openai_api_key="embedding-test-secret"))
    assert provider.embed(["code"]) == [[1, 0]]
    assert provider.answer("q", [{"source": "code"}]).status == "insufficient_context"
    assert hosts == ["api.openai.com", "api.anthropic.com"]


@pytest.mark.parametrize(
    "mode,profile", [("investigate", None), ("edit", None), ("edit", "node-test")]
)
def test_claude_decisions_only_advertise_authorized_actions(monkeypatch, mode, profile):
    def handler(request):
        payload = json.loads(request.content)
        schema = payload["output_config"]["format"]["schema"]
        actions = schema["properties"]["action"]["enum"]
        assert ("edit_file" in actions) == (mode == "edit")
        assert ("run_tests" in actions) == (profile is not None)
        assert "shell" not in actions
        args = dict.fromkeys(schema["properties"]["arguments"]["required"])
        return httpx.Response(
            200,
            json=completed(
                {
                    "plan": ["Inspect source"],
                    "summary": "Insufficient evidence",
                    "action": "finish",
                    "arguments": args,
                    "answer": {"status": "insufficient_context", "claims": []},
                }
            ),
        )

    mock_http(monkeypatch, handler)
    result = get_investigator(settings()).decide({"mode": mode, "test_profile": profile})
    assert result.action == "finish"


@pytest.mark.parametrize(
    "data",
    [
        {"stop_reason": "refusal", "content": []},
        {"stop_reason": "max_tokens", "content": []},
        {"stop_reason": "end_turn", "content": ["malformed"]},
        {"stop_reason": "end_turn", "content": [{"type": "tool_use", "name": "shell"}]},
        {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "private invalid output"}],
        },
        completed({"status": "answered", "claims": [], "extra": "private"}),
    ],
)
def test_claude_rejects_bad_outputs_without_reflecting_content(monkeypatch, data):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=data))
    for invoke, code in [
        (lambda: AnthropicProvider(settings()).answer("q", []), "invalid_answer"),
        (lambda: AnthropicInvestigator(settings()).decide({}), "invalid_agent_decision"),
    ]:
        with pytest.raises(DomainError) as error:
            invoke()
        assert error.value.code == code
        assert "private" not in error.value.message


@pytest.mark.parametrize(
    "status,code", [(401, "provider_auth"), (429, "provider_rate_limit"), (500, "provider_failed")]
)
def test_claude_http_errors_sanitized(monkeypatch, status, code):
    mock_http(monkeypatch, lambda request: httpx.Response(status, text="private key/source"))
    with pytest.raises(DomainError) as error:
        AnthropicInvestigator(settings()).decide({})
    assert error.value.code == code
    assert "private" not in error.value.message


def test_status_distinguishes_reasoning_and_embedding_availability(api, fake_download):
    prefix = imported(api)
    api.app.state.settings = settings()
    status = api.get(prefix + "/index").json()
    assert status["reasoning_configured"] is True
    assert status["configured"] is False
    assert status["reasoning_provider"] == "Anthropic"
    assert status["provider"] == "OpenAI"
    assert status["answer_model"] == "claude-sonnet-5"
    assert "claude-test-secret" not in json.dumps(status)
    api.app.state.settings = Settings(_env_file=None, openai_api_key="embedding-only")
    status = api.get(prefix + "/index").json()
    assert status["configured"] is True
    assert status["reasoning_configured"] is False


def test_claude_agent_runs_through_validated_tools_and_persists_model(
    api, fake_download, monkeypatch
):
    prefix = imported(api)
    api.app.state.settings = settings()
    files = api.get(prefix + "/files").json()["items"]
    file_id = next(file["id"] for file in files if file["path"] == "auth.py")
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        state = json.loads(payload["messages"][0]["content"])
        args = dict.fromkeys(
            payload["output_config"]["format"]["schema"]["properties"]["arguments"]["required"]
        )
        result = {
            "plan": ["Read login"],
            "summary": "Inspect login",
            "arguments": args,
            "answer": None,
        }
        if calls == 1:
            result["action"] = "read_file"
            args.update(file_id=file_id, start_line=1, end_line=3)
        else:
            assert "return email" in json.dumps(state)
            result.update(
                action="finish",
                answer={
                    "status": "answered",
                    "claims": [
                        {"text": "Login returns the supplied email.", "citation_ids": ["E1"]}
                    ],
                },
            )
        return httpx.Response(200, json=completed(result))

    mock_http(monkeypatch, handler)
    response = api.post(prefix + "/agent-runs", json={"task": "Inspect login"})
    assert response.status_code == 202, response.text
    run = api.get(prefix + "/agent-runs/" + response.json()["id"]).json()
    assert run["status"] == "completed", run
    assert run["model"] == "claude-sonnet-5"
    assert run["result"]["citations"][0]["file_id"] == file_id
    assert calls == 2


@pytest.mark.parametrize("block_type", ["thinking", "redacted_thinking"])
def test_claude_parses_answer_text_alongside_thinking(monkeypatch, block_type):
    answer = {"status": "insufficient_context", "claims": []}
    payload = completed(answer)
    payload["content"].insert(0, {"type": block_type, "thinking": "not answer JSON"})
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=payload))
    assert AnthropicProvider(settings()).answer("q", []).status == "insufficient_context"
    payload["content"][1]["text"] = json.dumps(
        {
            "plan": ["Inspect source"],
            "summary": "Insufficient evidence",
            "action": "finish",
            "arguments": {},
            "answer": answer,
        }
    )
    assert AnthropicInvestigator(settings()).decide({}).action == "finish"
    payload["content"] = payload["content"][:1]
    with pytest.raises(DomainError) as error:
        AnthropicInvestigator(settings()).decide({})
    assert error.value.code == "invalid_agent_decision"
