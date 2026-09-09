import math
from collections.abc import Sequence

from codeatlas.core.errors import DomainError


def normalize(vector: Sequence[float], dimensions: int | None = None) -> list[float]:
    if not isinstance(vector, (list, tuple)):
        raise DomainError("invalid_embedding", "Provider returned invalid embeddings.", 502)
    if not 1 <= len(vector) <= 4096 or (dimensions is not None and len(vector) != dimensions):
        raise DomainError("invalid_embedding", "Embedding dimensions do not match the index.", 502)
    if any(type(v) not in (float, int) or not math.isfinite(v) for v in vector):
        raise DomainError("invalid_embedding", "Provider returned invalid embeddings.", 502)
    norm = math.hypot(*vector)
    if not math.isfinite(norm) or norm == 0:
        raise DomainError("invalid_embedding", "Provider returned invalid embeddings.", 502)
    return [v / norm for v in vector]


def rank(query: list[float], candidates: list[tuple[str, list[float]]], k: int = 6) -> list[str]:
    unit = normalize(query)
    scores = [
        (sum(a * b for a, b in zip(unit, normalize(v, len(unit)), strict=True)), key)
        for key, v in candidates
    ]
    return [key for score, key in sorted(scores, key=lambda row: (-row[0], row[1]))[:k]]
