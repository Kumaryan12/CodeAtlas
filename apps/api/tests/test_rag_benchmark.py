import math

import pytest

from codeatlas.ai.provider import OpenAIProvider
from codeatlas.core.config import Settings
from codeatlas.evaluation.rag import ranking_metrics, run
from codeatlas.services.qa import fingerprint


def test_metrics_credit_duplicates_once_and_missing_evidence():
    metrics = ranking_metrics(["a", "a", "wrong"], ["a", "b"], 3)
    assert metrics["precision@3"] == pytest.approx(1 / 3)
    assert metrics["recall@3"] == 0.5
    assert metrics["mrr@3"] == 1
    assert metrics["ndcg@3"] == pytest.approx(1 / (1 + 1 / math.log2(3)))
    assert metrics["complete_evidence@3"] == 0
    with pytest.raises(ValueError):
        ranking_metrics([], [], 3)


def test_local_provider_never_calls_remote_embeddings(monkeypatch):
    from codeatlas.ai import local_embeddings

    monkeypatch.setattr(local_embeddings, "embed", lambda texts: [[1.0] for _ in texts])
    settings = Settings(_env_file=None, embedding_provider="local")
    provider = OpenAIProvider(settings)
    monkeypatch.setattr(provider, "_post", lambda *_: pytest.fail("Remote embeddings called"))
    assert provider.embed(["source"]) == [[1.0]]
    assert fingerprint(settings).startswith("local:")
    assert len(fingerprint(settings)) <= 200
    assert fingerprint(settings) != fingerprint(Settings(_env_file=None))


def test_offline_corpus_validates_labels_and_separates_negatives():
    report = run(Settings(_env_file=None), offline=True)
    assert report["retrieval"]["lexical"]["case_count"] == 18
    assert len(report["corpus_sha256"]) == 64
    assert report["answers"] == []


def test_local_real_model_preserves_tail_and_normalizes():
    import os

    if os.environ.get("CODEATLAS_TEST_LOCAL_EMBEDDINGS") != "1":
        pytest.skip("Opt in after preparing local model weights")
    from codeatlas.ai.local_embeddings import embed

    head = "repository source " * 300
    vectors = embed([head, head + " currency exchange rate conversion " * 100, "", "hello"])
    assert all(len(vector) == 384 for vector in vectors)
    assert all(
        sum(value * value for value in vector) == pytest.approx(1, abs=1e-5) for vector in vectors
    )
    assert sum((a - b) ** 2 for a, b in zip(vectors[0], vectors[1], strict=True)) > 0.01
    assert embed([]) == []


def test_report_keeps_service_errors_in_outcome_denominator():
    from codeatlas.evaluation.rag_report import render

    report = run(Settings(_env_file=None), offline=True)
    report["answers"] = [
        {
            "id": "no_password",
            "expected": [],
            "error": "provider_timeout",
            "expected_outcome": False,
            "http_usage": [],
        }
    ]
    rendered = render(report)
    assert "provider/service errors: 1" in rendered
    assert "0/1 (errors count as failures)" in rendered
    assert "provider_timeout" in rendered
    with pytest.raises(ValueError, match="Unknown"):
        run(Settings(_env_file=None), offline=True, case_ids={"nonexistent"})
