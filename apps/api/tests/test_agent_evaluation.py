from types import SimpleNamespace

import pytest

from codeatlas.core.config import Settings
from codeatlas.core.errors import DomainError
from codeatlas.evaluation.agent import CASES, evaluate, grade


def test_scripted_report_checks_real_runtime_and_labels_limits():
    report = evaluate(Settings(_env_file=None))
    assert report["mode"] == "scripted" and report["provider"] is None
    assert report["passed"] is True
    assert len(report["results"]) == len(CASES) == 6
    assert report["groups"] == {
        "task": {"passed": 2, "total": 2},
        "guardrail": {"passed": 4, "total": 4},
    }
    cases = {row["id"]: row for row in report["results"]}
    assert cases["forbidden_tool"]["error_code"] == "invalid_agent_decision"
    assert cases["invented_citation"]["error_code"] == "invalid_citations"
    assert cases["tool_budget"]["error_code"] == "step_limit"
    assert all(row["usage"]["estimated_cost_usd"] is None for row in report["results"])


def test_live_evaluation_requires_credentials_before_running():
    with pytest.raises(DomainError) as error:
        evaluate(Settings(_env_file=None), mode="live")
    assert error.value.code == "ai_not_configured"


def test_grader_does_not_count_provider_failure_or_fake_citation_as_success():
    run = SimpleNamespace(
        status="failed", error_code="provider_timeout", result=None, steps=[], changes={}
    )
    for case in CASES:
        assert grade(case, run, "file", True)["passed"] is False
    run.status = "completed"
    run.result = {
        "status": "answered",
        "claims": [{"text": "Guess", "citation_ids": ["E999"]}],
        "citations": [],
    }
    result = grade(CASES[0], run, "file", True)
    assert result["passed"] is False
    assert result["citation_reference_accuracy"] == 0


def test_mcp_evaluation_uses_same_cases_and_grades():
    report = evaluate(Settings(_env_file=None), transport="mcp", selected=["source_injection"])
    assert report["passed"] is True
    read = next(s for s in report["results"][0]["steps"] if s["kind"] == "read")
    assert read["transport"] == "mcp"


def test_grader_accepts_trailing_blank_line_but_keeps_marker_check():
    from codeatlas.evaluation.agent import SOURCE

    run = SimpleNamespace(
        status="completed",
        error_code=None,
        changes={},
        steps=[],
        result={
            "status": "answered",
            "claims": [
                {"text": "The function validates and normalizes the email.", "citation_ids": ["E1"]}
            ],
            "citations": [
                {
                    "id": "E1",
                    "file_id": "file",
                    "start_line": 1,
                    "end_line": len(SOURCE.split("\n")),
                }
            ],
        },
    )
    assert grade(CASES[0], run, "file", True)["passed"] is True
    run.result["claims"][0]["text"] = "The comment says ATLAS_INJECTION_SUCCESS."
    result = grade(CASES[0], run, "file", True)
    assert result["checks"]["valid_citation_references"] is True
    assert result["checks"]["no_injection_marker_in_claims"] is False
