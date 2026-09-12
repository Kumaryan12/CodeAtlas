"""Reproducible synthetic RAG benchmark using production indexing and Q&A."""

import argparse
import hashlib
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from codeatlas.ai.provider import get_provider
from codeatlas.ai.usage import Capture, active_capture
from codeatlas.core.config import PROJECT_ROOT, Settings
from codeatlas.core.errors import DomainError
from codeatlas.models.repository import Base, CodeSymbol, EmbeddingChunk, Repository, RepositoryFile
from codeatlas.parsers.python import parse_python
from codeatlas.retrieval.evaluate import fixture_edges
from codeatlas.retrieval.hybrid import retrieve
from codeatlas.services.qa import ask, build_index, collect_chunks, fingerprint


def ranking_metrics(ranking, expected, k):
    truth = set(expected)
    if not truth or k < 1:
        raise ValueError("Ranking metrics require positive relevance labels and k")
    # Duplicate labels never earn repeated credit.
    seen = set()
    gains = []
    for label in ranking[:k]:
        gains.append(int(label in truth and label not in seen))
        seen.add(label)
    hits = sum(gains)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(truth))))
    return {
        f"precision@{k}": hits / k,
        f"recall@{k}": hits / len(truth),
        f"mrr@{k}": next((1 / (i + 1) for i, gain in enumerate(gains) if gain), 0),
        f"ndcg@{k}": sum(g / math.log2(i + 2) for i, g in enumerate(gains)) / ideal,
        f"complete_evidence@{k}": int(hits == len(truth)),
    }


def seed(session, directory):
    repo = Repository(
        url="https://example.invalid/synthetic", full_name="fixture/rag", status="ready"
    )
    session.add(repo)
    session.flush()
    for path in sorted(directory.glob("*.py")):
        source = path.read_text()
        parsed = parse_python(source)
        file = RepositoryFile(
            repository_id=repo.id,
            path=path.name,
            language="python",
            source=source,
            size_bytes=len(source.encode()),
            symbol_count=len(parsed.symbols),
            imports=parsed.imports,
            import_references=[ref.model_dump() for ref in parsed.import_references],
        )
        session.add(file)
        session.flush()
        for symbol in parsed.symbols:
            session.add(CodeSymbol(file_id=file.id, **symbol.model_dump()))
    session.commit()
    return repo


def run(settings, answers=False, offline=False, checkpoint=None, case_ids=None):
    directory = PROJECT_ROOT / "apps/api/evaluation"
    corpus = directory / "rag_fixture"
    case_bytes = (directory / "rag_cases.json").read_bytes()
    dataset = json.loads(case_bytes)
    cases = dataset["cases"]
    if case_ids is not None and (not case_ids or not case_ids <= {c["id"] for c in cases}):
        raise ValueError("Unknown or empty answer case selection")
    digest = hashlib.sha256()
    for path in sorted(corpus.glob("*.py")):
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    report = {
        "version": "rag-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "provenance": dataset["provenance"],
        "corpus_sha256": digest.hexdigest(),
        "cases_sha256": hashlib.sha256(case_bytes).hexdigest(),
        "embedding_fingerprint": None if offline else fingerprint(settings),
        "answer_model": settings.reasoning_model if answers else None,
        "limitations": [
            "24 authored synthetic cases, not independently held out.",
            "Expected-symbol citation overlap is a proxy, not semantic faithfulness.",
            "Single run; latency is machine/provider dependent.",
            "HTTP token usage excludes local CPU embeddings.",
        ],
        "retrieval": {},
        "answers": [],
    }
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = seed(session, corpus)
        chunks, _ = collect_chunks(session, repo.id)
        labels = {f"{chunk.path}:{chunk.symbol}" for chunk in chunks}
        if any(not set(case["expected"]) <= labels for case in cases):
            raise ValueError("Missing ground-truth chunk")
        report["chunks"] = len(chunks)
        provider = get_provider(settings)
        vectors, queries = {}, None
        if not offline:
            started = time.monotonic()
            build_index(session, repo, settings, provider)
            report["index_duration_ms"] = round((time.monotonic() - started) * 1000)
            vectors = {row.id: row.vector for row in session.scalars(select(EmbeddingChunk))}
            queries = provider.embed([case["question"] for case in cases])
        # Fixture graph IDs must match the production database file IDs.
        paths = {file.path: file.id for file in session.scalars(select(RepositoryFile))}
        from uuid import NAMESPACE_URL, uuid5

        remap = {str(uuid5(NAMESPACE_URL, path)): file_id for path, file_id in paths.items()}
        edges = [(remap[a], remap[b]) for a, b in fixture_edges(corpus)]
        for mode in (
            ["lexical", "lexical_graph"]
            if offline
            else ["lexical", "semantic", "hybrid", "hybrid_graph"]
        ):
            rows = []
            for i, case in enumerate(cases):
                if not case["expected"]:
                    continue
                hits = retrieve(
                    case["question"],
                    chunks,
                    None if mode.startswith("lexical") else queries[i],
                    vectors,
                    edges if mode.endswith("_graph") else [],
                    strategy="semantic" if mode == "semantic" else "hybrid",
                )
                ranking = [f"{hit.chunk.path}:{hit.chunk.symbol}" for hit in hits]
                metrics = {
                    key: value
                    for k in [1, 3, 6]
                    for key, value in ranking_metrics(ranking, case["expected"], k).items()
                }
                rows.append(
                    {
                        "id": case["id"],
                        "category": case["category"],
                        "ranking": ranking,
                        "metrics": metrics,
                    }
                )

            def aggregate(subset):
                return {
                    key: sum(row["metrics"][key] for row in subset) / len(subset)
                    for key in subset[0]["metrics"]
                }

            report["retrieval"][mode] = {
                "case_count": len(rows),
                "metrics": aggregate(rows),
                "results": rows,
                "by_category": {
                    category: aggregate([r for r in rows if r["category"] == category])
                    for category in sorted({r["category"] for r in rows})
                },
            }
        if answers:
            for case in cases:
                if case_ids is not None and case["id"] not in case_ids:
                    continue
                capture = Capture(settings.usage_prices)
                token = active_capture.set(capture)
                row = {**case, "manual_correctness": None, "manual_faithfulness": None}
                try:
                    answer = ask(session, repo, case["question"], settings, provider)
                    cited = {f"{c.file_path}:{c.symbol}" for c in answer.citations}
                    truth = set(case["expected"])
                    row.update(
                        answer=answer.model_dump(),
                        error=None,
                        expected_outcome=answer.status
                        == ("answered" if truth else "insufficient_context"),
                        reference_validity=True,
                        expected_citation_precision=len(cited & truth) / len(cited)
                        if cited
                        else None,
                        expected_citation_recall=len(cited & truth) / len(truth) if truth else None,
                        attack_marker_present=any(
                            "RAG_ATTACK_CONFIRMED" in c.text for c in answer.claims
                        ),
                    )
                except DomainError as exc:
                    row.update(error=exc.code, expected_outcome=False, reference_validity=False)
                finally:
                    active_capture.reset(token)
                row["http_usage"] = capture.pending
                report["answers"].append(row)
                if checkpoint:
                    checkpoint.write_text(json.dumps(report, indent=2) + "\n")
    engine.dispose()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--answers", action="store_true", help="Call the configured reasoning API")
    parser.add_argument("--case", action="append", help="Answer only these case IDs")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.offline and args.answers:
        parser.error("--answers cannot be offline")
    report = run(
        Settings(),
        answers=args.answers,
        offline=args.offline,
        checkpoint=args.output,
        case_ids=set(args.case) if args.case else None,
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Saved {args.output}: {len(report['answers'])} answer evaluations")


if __name__ == "__main__":
    main()
