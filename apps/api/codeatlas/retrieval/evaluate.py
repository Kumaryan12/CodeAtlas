"""Small real-embedding retrieval eval; explicit --live opts into provider calls."""

import argparse
import json
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from codeatlas.ai.provider import get_provider
from codeatlas.core.config import PROJECT_ROOT, Settings
from codeatlas.core.errors import DomainError
from codeatlas.dependencies.graph import build_graph
from codeatlas.models.repository import CodeSymbol, RepositoryFile
from codeatlas.parsers.python import parse_python
from codeatlas.retrieval.chunks import chunk_file
from codeatlas.retrieval.hybrid import RETRIEVAL_VERSION, retrieve
from codeatlas.schemas.graph import GraphFile


def metrics(retrieved: list[list[str]], expected: list[list[str]], k: int) -> dict[str, float]:
    if (
        not retrieved
        or len(retrieved) != len(expected)
        or k < 1
        or any(not row for row in expected)
    ):
        raise ValueError("Expected paired, nonempty evaluation cases and positive k")
    recall = reciprocal = 0.0
    for ranking, relevant in zip(retrieved, expected, strict=True):
        truth = set(relevant)
        recall += len(set(ranking[:k]) & truth) / len(truth)
        reciprocal += next((1 / (i + 1) for i, item in enumerate(ranking[:k]) if item in truth), 0)
    return {f"recall@{k}": recall / len(expected), f"mrr@{k}": reciprocal / len(expected)}


def fixture_chunks(directory: Path):
    chunks = []
    for path in sorted(directory.glob("*.py")):
        source = path.read_text()
        file = RepositoryFile(
            id=str(uuid5(NAMESPACE_URL, path.name)),
            path=path.name,
            language="python",
            source=source,
        )
        parsed = parse_python(source)
        symbols = [CodeSymbol(**symbol.model_dump()) for symbol in parsed.symbols]
        chunks.extend(chunk_file(file, symbols)[0])
    return chunks


def fixture_edges(directory: Path):
    files = []
    for path in sorted(directory.glob("*.py")):
        parsed = parse_python(path.read_text())
        files.append(
            GraphFile(
                id=str(uuid5(NAMESPACE_URL, path.name)),
                path=path.name,
                language="python",
                imports=parsed.imports,
                import_references=parsed.import_references,
            )
        )
    graph = build_graph("evaluation", files, [])
    return [(edge.source, edge.target) for edge in graph.edges]


def compare(cases, chunks, queries, vectors, edges):
    modes = (
        ["semantic", "hybrid", "hybrid_graph"]
        if queries is not None
        else ["lexical", "lexical_graph"]
    )
    expected = [case["expected"] for case in cases]
    report = {}
    for mode in modes:
        rankings = []
        for i, case in enumerate(cases):
            results = retrieve(
                case["question"],
                chunks,
                queries[i] if queries is not None else None,
                vectors,
                edges if mode.endswith("_graph") else [],
                strategy="semantic" if mode == "semantic" else "hybrid",
            )
            rankings.append([f"{item.chunk.path}:{item.chunk.symbol}" for item in results])
        report[mode] = {
            **metrics(rankings, expected, 1),
            **metrics(rankings, expected, 3),
            **metrics(rankings, expected, 6),
            "results": [
                {**case, "retrieved": ranking}
                for case, ranking in zip(cases, rankings, strict=True)
            ],
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--live",
        action="store_true",
        help="Compare semantic, hybrid, and graph retrieval using real embeddings",
    )
    mode.add_argument(
        "--offline",
        action="store_true",
        help="Evaluate lexical retrieval with and without graph expansion; no provider calls",
    )
    args = parser.parse_args()
    settings = Settings()
    directory = PROJECT_ROOT / "apps/api/evaluation"
    chunks = fixture_chunks(directory / "fixture")
    edges = fixture_edges(directory / "fixture")
    cases = json.loads((directory / "questions.json").read_text())
    started = time.monotonic()
    queries = None
    vectors = {}
    try:
        if args.live:
            provider = get_provider(settings)
            embedded = provider.embed([chunk.embedding_text() for chunk in chunks])
            queries = provider.embed([case["question"] for case in cases])
            if len(queries) != len(cases):
                raise DomainError(
                    "invalid_embedding", "Incomplete evaluation query embeddings.", 502
                )
            vectors = {chunk.id: vector for chunk, vector in zip(chunks, embedded, strict=True)}
        report = compare(cases, chunks, queries, vectors, edges)
    except DomainError as exc:
        parser.exit(2, f"{exc.code}: {exc.message}\n")
    print(
        json.dumps(
            {
                "retrieval_version": RETRIEVAL_VERSION,
                "mode": "live" if args.live else "offline_lexical_only",
                "embedding_model": settings.embedding_model if args.live else None,
                "cases": len(cases),
                "chunks": len(chunks),
                "dependency_edges": len(edges),
                "duration_ms": round((time.monotonic() - started) * 1000),
                "comparisons": report,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
