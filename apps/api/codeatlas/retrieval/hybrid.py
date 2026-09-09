"""Bounded code retrieval: BM25, explicit symbols, rank fusion, and one-hop imports."""

import math
import re
from collections import Counter
from dataclasses import dataclass

from codeatlas.retrieval.chunks import Chunk
from codeatlas.retrieval.vectors import normalize

RETRIEVAL_VERSION = "hybrid-v1"
CHANNEL_LIMIT = 50
RRF_CONSTANT = 60
STOP_WORDS = frozenset(
    (
        "a an the is are was were of to in for how does do what where which and or this that "
        "with from code function method return def const import"
    ).split()
)


def tokens(text: str) -> list[str]:
    # Preserve full identifiers as well as camelCase/snake_case components.
    words = re.findall(r"\w+", text, re.UNICODE)
    output = []
    for word in words:
        full = word.casefold()
        pieces = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", word).replace("_", " ").casefold().split()
        output.extend(dict.fromkeys([full, *pieces]))
    return [word for word in output if word not in STOP_WORDS and len(word) > 1]


@dataclass(frozen=True)
class RankedChunk:
    chunk: Chunk
    semantic_score: float | None
    keyword_score: float
    symbol_score: float
    fusion_score: float
    reason: str
    via_file_id: str | None = None


def bm25(question: str, chunks: list[Chunk]) -> list[float]:
    query = set(tokens(question)[:64])
    documents = [Counter(tokens(f"{c.path} {c.symbol or ''} {c.source}")) for c in chunks]
    frequencies = Counter(term for doc in documents for term in doc)
    lengths = [sum(doc.values()) for doc in documents]
    average = sum(lengths) / max(len(lengths), 1) or 1
    scores = []
    for doc, length in zip(documents, lengths, strict=True):
        score = 0.0
        for term in sorted(query):
            count = doc[term]
            if count:
                df = frequencies[term]
                inverse = math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
                score += inverse * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * length / average))
        scores.append(score)
    return scores


def retrieve(
    question: str,
    chunks: list[Chunk],
    query: list[float] | None,
    vectors: dict[str, list[float]],
    edges: list[tuple[str, str]],
    *,
    strategy: str = "hybrid",
    k: int = 6,
) -> list[RankedChunk]:
    """query=None is lexical-only evaluation, never a silent production fallback."""
    if not 1 <= k <= 6 or strategy not in {"semantic", "hybrid"}:
        raise ValueError("Unsupported retrieval strategy or context budget")
    if not chunks:
        return []
    if strategy == "semantic" and query is None:
        raise ValueError("Semantic retrieval requires a query embedding")

    def stable(i):
        return (chunks[i].path, chunks[i].start_line, chunks[i].id)

    unit = normalize(query) if query is not None else None
    semantic = [
        sum(a * b for a, b in zip(unit, normalize(vectors[c.id], len(unit)), strict=True))
        if unit is not None
        else None
        for c in chunks
    ]
    keyword = bm25(question, chunks) if strategy == "hybrid" else [0.0] * len(chunks)
    identifiers = set(re.findall(r"[#\w$]+", question.casefold()))
    paths = {path.rstrip(".") for path in re.findall(r"[\w./$#-]+", question.casefold())}
    symbol = [
        float(
            2 * bool(c.symbol and c.symbol.casefold() in identifiers)
            + bool(c.path.casefold() in paths)
        )
        if strategy == "hybrid"
        else 0.0
        for c in chunks
    ]
    fusion = [0.0] * len(chunks)
    for scores, weight in [(semantic, 1), (keyword, 1), (symbol, 2)]:
        ranking = sorted(
            (
                i
                for i, score in enumerate(scores)
                if score is not None and (scores is semantic or score > 0)
            ),
            key=lambda i: (-scores[i], *stable(i)),
        )[:CHANNEL_LIMIT]
        for position, i in enumerate(ranking, 1):
            fusion[i] += weight / (RRF_CONSTANT + position)
    if strategy == "semantic":
        order = sorted(range(len(chunks)), key=lambda i: (-semantic[i], *stable(i)))
    else:
        order = sorted(
            (i for i in range(len(chunks)) if fusion[i] > 0), key=lambda i: (-fusion[i], *stable(i))
        )
    budget = min(2, k // 3) if edges and strategy == "hybrid" else 0
    base_count = k - budget
    selected = order[:base_count]
    graph_via: dict[int, str] = {}
    if budget:
        seeds = list(dict.fromkeys(chunks[i].file_id for i in selected[:2]))
        neighbors: dict[str, str] = {}
        unique_edges = sorted(set(edges))
        for seed in seeds:
            for source, target in unique_edges:
                if source == seed and target != seed:
                    neighbors.setdefault(target, seed)
                if target == seed and source != seed:
                    neighbors.setdefault(source, seed)
        used_files = {chunks[i].file_id for i in selected}
        # One excerpt per new adjacent file; never recurse or expand unresolved imports.
        expansion_order = sorted(range(len(chunks)), key=lambda i: (-fusion[i], *stable(i)))
        for i in expansion_order:
            file_id = chunks[i].file_id
            if file_id in neighbors and file_id not in used_files:
                selected.append(i)
                graph_via[i] = neighbors[file_id]
                used_files.add(file_id)
                if len(graph_via) >= budget:
                    break
        selected = selected[:k]
    for i in order:
        if len(selected) >= k:
            break
        if i not in selected:
            selected.append(i)
    return [
        RankedChunk(
            chunks[i],
            semantic[i],
            keyword[i],
            symbol[i],
            fusion[i],
            "dependency" if i in graph_via else "semantic" if strategy == "semantic" else "hybrid",
            graph_via.get(i),
        )
        for i in selected
    ]
