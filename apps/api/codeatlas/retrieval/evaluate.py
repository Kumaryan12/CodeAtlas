"""Small real-embedding retrieval eval; explicit --live opts into provider calls."""

import argparse
import json
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from codeatlas.ai.provider import get_provider
from codeatlas.core.config import PROJECT_ROOT, Settings
from codeatlas.core.errors import DomainError
from codeatlas.models.repository import CodeSymbol, RepositoryFile
from codeatlas.parsers.python import parse_python
from codeatlas.retrieval.chunks import chunk_file
from codeatlas.retrieval.vectors import rank


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Send evaluation fixture excerpts and questions for embeddings",
    )
    args = parser.parse_args()
    if not args.live:
        parser.error(
            "Pass --live to run the real-provider evaluation. "
            "No synthetic semantic scores are reported."
        )
    settings = Settings()
    directory = PROJECT_ROOT / "apps/api/evaluation"
    chunks = fixture_chunks(directory / "fixture")
    cases = json.loads((directory / "questions.json").read_text())
    provider = get_provider(settings)
    started = time.monotonic()
    try:
        vectors = provider.embed([chunk.embedding_text() for chunk in chunks])
        queries = provider.embed([case["question"] for case in cases])
        candidates = [(chunk.id, vector) for chunk, vector in zip(chunks, vectors, strict=True)]
        labels = {chunk.id: f"{chunk.path}:{chunk.symbol}" for chunk in chunks}
        rankings = [[labels[key] for key in rank(query, candidates, 3)] for query in queries]
    except DomainError as exc:
        parser.exit(2, f"{exc.code}: {exc.message}\n")
    expected = [case["expected"] for case in cases]
    print(
        json.dumps(
            {
                "embedding_model": settings.embedding_model,
                "cases": len(cases),
                **metrics(rankings, expected, 1),
                **metrics(rankings, expected, 3),
                "duration_ms": round((time.monotonic() - started) * 1000),
                "results": [
                    {**case, "retrieved": ranking}
                    for case, ranking in zip(cases, rankings, strict=True)
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
