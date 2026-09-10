import json

import httpx
import pytest
from test_agent import ScriptedInvestigator, decision, start
from test_qa import imported, mock_http

from codeatlas.ai.anthropic import AnthropicInvestigator
from codeatlas.ai.usage import (
    Capture,
    TokenPrices,
    active_capture,
    drain_usage,
    record_usage,
    summarize_usage,
)


def test_provider_usage_cache_accounting_and_pricing():
    token = active_capture.set(
        Capture(
            {
                "anthropic:fixture": TokenPrices(
                    input=2, output=10, cached_input=0.2, cache_write=2.5
                ),
                "openai:fixture": TokenPrices(
                    input=2, output=10, cached_input=0.2, cache_write=2.5
                ),
            }
        )
    )
    try:
        record_usage(
            "https://api.anthropic.com/v1/messages",
            "fixture",
            {
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 50,
                    "cache_creation_input_tokens": 10,
                }
            },
            12,
        )
        record_usage(
            "https://api.openai.com/v1/responses",
            "fixture",
            {
                "usage": {
                    "input_tokens": 160,
                    "output_tokens": 20,
                    "input_tokens_details": {"cached_tokens": 50, "cache_write_tokens": 10},
                }
            },
            18,
        )
        rows = drain_usage()
        assert rows[0]["estimated_cost_usd"] == pytest.approx(0.000435)
        assert rows[1]["estimated_cost_usd"] == pytest.approx(0.000435)
        summary = summarize_usage([{"kind": "model", "usage": rows}])
        assert summary["known_input_tokens"] == 320
        assert summary["known_output_tokens"] == 40
        assert summary["provider_duration_ms"] == 30
        assert summary["tokens_complete"] is True
        assert summary["estimated_cost_usd"] == pytest.approx(0.000870)
        assert drain_usage() == []
        # An interrupted call without a response must not make a partial bill look complete.
        assert (
            summarize_usage([{"kind": "model", "usage": rows}, {"kind": "model"}])[
                "estimated_cost_usd"
            ]
            is None
        )
    finally:
        active_capture.reset(token)


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"input_tokens": True, "output_tokens": -1},
        {"input_tokens": "100", "output_tokens": 1},
    ],
)
def test_missing_or_malformed_usage_is_unknown_not_zero(usage):
    token = active_capture.set(Capture({}))
    try:
        record_usage("https://api.anthropic.com/v1/messages", "fixture", {"usage": usage}, 1)
        summary = summarize_usage([{"kind": "model", "usage": drain_usage()}])
        assert summary["tokens_complete"] is False
        assert summary["estimated_cost_usd"] is None
    finally:
        active_capture.reset(token)


def test_missing_cache_rate_never_invents_cost():
    token = active_capture.set(Capture({"anthropic:fixture": TokenPrices(input=2, output=10)}))
    try:
        record_usage(
            "https://api.anthropic.com/v1/messages",
            "fixture",
            {
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 10,
                }
            },
            1,
        )
        assert drain_usage()[0]["estimated_cost_usd"] is None
    finally:
        active_capture.reset(token)


def test_embedding_and_failed_transport_usage():
    token = active_capture.set(Capture({"openai:embed": TokenPrices(input=0.02, output=0)}))
    try:
        record_usage(
            "https://api.openai.com/v1/embeddings", "embed", {"usage": {"prompt_tokens": 100}}, 5
        )
        record_usage("https://api.openai.com/v1/responses", "fixture", None, 10)
        rows = drain_usage()
        assert rows[0]["operation"] == "embedding"
        assert rows[0]["estimated_cost_usd"] == pytest.approx(0.000002)
        assert rows[1]["response_received"] is False
        assert rows[1]["input_tokens"] is None
        assert summarize_usage([{"usage": rows}])["estimated_cost_usd"] is None
    finally:
        active_capture.reset(token)


@pytest.mark.parametrize("valid", [True, False])
def test_usage_persisted_for_valid_and_invalid_model_decisions(
    api, fake_download, monkeypatch, valid
):
    prefix = imported(api)
    api.app.state.settings.anthropic_api_key = type(api.app.state.settings.anthropic_api_key)(
        "private-key"
    )
    body = (
        decision("finish", answer={"status": "insufficient_context", "claims": []})
        if valid
        else {"private": "source"}
    )
    mock_http(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={
                "stop_reason": "end_turn",
                "content": [
                    {"type": "text", "text": json.dumps(body.model_dump() if valid else body)}
                ],
                "usage": {"input_tokens": 123, "output_tokens": 12},
            },
        ),
    )
    result = start(api, prefix, AnthropicInvestigator(api.app.state.settings))
    assert result["status"] == ("completed" if valid else "failed")
    assert result["usage_summary"]["known_input_tokens"] == 123
    assert result["steps"][0]["usage"][0]["model"] == "claude-sonnet-5"
    assert "private" not in json.dumps(result)
    assert active_capture.get() is None
    # A scripted run cannot inherit another run's measured usage.
    scripted = start(
        api,
        prefix,
        ScriptedInvestigator(
            [decision("finish", answer={"status": "insufficient_context", "claims": []})]
        ),
    )
    assert scripted["usage_summary"]["recorded_calls"] == 0
    assert scripted["usage_summary"]["estimated_cost_usd"] is None


def test_failed_http_call_is_recorded_as_unmeasured(api, fake_download, monkeypatch):
    prefix = imported(api)
    api.app.state.settings.anthropic_api_key = type(api.app.state.settings.anthropic_api_key)(
        "fixture"
    )
    mock_http(monkeypatch, lambda request: httpx.Response(429, text="private billing payload"))
    result = start(api, prefix, AnthropicInvestigator(api.app.state.settings))
    assert result["error_code"] == "provider_rate_limit"
    assert result["usage_summary"]["recorded_calls"] == 1
    assert result["usage_summary"]["tokens_complete"] is False
    assert result["usage_summary"]["estimated_cost_usd"] is None
    assert result["steps"][0]["usage"][0]["response_received"] is True
    assert result["steps"][0]["usage"][0]["http_status"] == 429
    assert "private" not in json.dumps(result)
