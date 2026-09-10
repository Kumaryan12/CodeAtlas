import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from codeatlas.ai.provider import AIProvider
from codeatlas.core.config import Settings
from codeatlas.core.errors import DomainError
from codeatlas.models.repository import (
    CodeSymbol,
    EmbeddingChunk,
    Repository,
    RepositoryFile,
    SemanticIndex,
)
from codeatlas.retrieval.chunks import CHUNK_VERSION, MAX_CHUNKS, MAX_INDEX_BYTES, Chunk, chunk_file
from codeatlas.retrieval.hybrid import RETRIEVAL_VERSION, retrieve
from codeatlas.retrieval.vectors import normalize
from codeatlas.schemas.qa import AskResponse, Citation, IndexStatus, RetrievalHit, RetrievalResponse
from codeatlas.services.dependency_graph import snapshot_graph

logger = logging.getLogger("codeatlas.qa")


def fingerprint(settings: Settings) -> str:
    return f"openai:{settings.embedding_model}:{CHUNK_VERSION}"


def index_status(session: Session, repository: Repository, settings: Settings) -> IndexStatus:
    index = session.get(SemanticIndex, repository.id)
    return IndexStatus(
        status="not_indexed"
        if index is None
        else "ready"
        if index.fingerprint == fingerprint(settings)
        else "stale",
        configured=bool(settings.openai_api_key.get_secret_value().strip()),
        provider="OpenAI",
        reasoning_configured=settings.reasoning_configured,
        reasoning_provider="Anthropic" if settings.reasoning_provider == "anthropic" else "OpenAI",
        reasoning_key_name=settings.reasoning_key_name,
        embedding_model=settings.embedding_model,
        answer_model=settings.reasoning_model,
        chunk_count=index.chunk_count if index else 0,
        skipped_long_lines=index.skipped_long_lines if index else 0,
        indexed_at=index.indexed_at.isoformat() if index else None,
    )


def collect_chunks(session: Session, repository_id: str) -> tuple[list[Chunk], int]:
    files = session.scalars(
        select(RepositoryFile)
        .where(RepositoryFile.repository_id == repository_id)
        .order_by(RepositoryFile.path)
    )
    by_file: dict[str, list[CodeSymbol]] = {}
    for symbol in session.scalars(
        select(CodeSymbol).join(RepositoryFile).where(RepositoryFile.repository_id == repository_id)
    ):
        by_file.setdefault(symbol.file_id, []).append(symbol)
    chunks: list[Chunk] = []
    skipped = size = 0
    for file in files:
        batch, omitted = chunk_file(file, by_file.get(file.id, []))
        skipped += omitted
        chunks.extend(batch)
        size += sum(len(chunk.embedding_text().encode("utf-8")) for chunk in batch)
        if len(chunks) > MAX_CHUNKS or size > MAX_INDEX_BYTES:
            raise DomainError(
                "index_too_large",
                "Semantic indexing supports up to 2,000 chunks and 2 MB of excerpts. "
                "Use a smaller repository.",
                422,
            )
    if not chunks:
        raise DomainError(
            "no_indexable_code", "No eligible nonempty source excerpts were found.", 422
        )
    return chunks, skipped


def build_index(
    session: Session, repository: Repository, settings: Settings, provider: AIProvider
) -> IndexStatus:
    status = index_status(session, repository, settings)
    if status.status == "ready":
        return status
    chunks, skipped = collect_chunks(session, repository.id)
    vectors: list[list[float]] = []
    start = time.monotonic()
    for offset in range(0, len(chunks), 16):
        if time.monotonic() - start > 90:
            raise DomainError(
                "index_timeout",
                "Indexing exceeded its time budget. Use a smaller repository or retry later.",
                504,
            )
        batch = chunks[offset : offset + 16]
        embedded = provider.embed([chunk.embedding_text() for chunk in batch])
        if len(embedded) != len(batch):
            raise DomainError(
                "invalid_embedding", "Provider returned an incomplete embedding batch.", 502
            )
        for vector in embedded:
            vectors.append(normalize(vector, len(vectors[0]) if vectors else None))
    # Only publish complete indexes. Failed calls leave the previous index intact.
    session.execute(delete(EmbeddingChunk).where(EmbeddingChunk.repository_id == repository.id))
    session.execute(delete(SemanticIndex).where(SemanticIndex.repository_id == repository.id))
    session.add(
        SemanticIndex(
            repository_id=repository.id,
            fingerprint=fingerprint(settings),
            dimensions=len(vectors[0]),
            chunk_count=len(chunks),
            skipped_long_lines=skipped,
            indexed_at=datetime.now(UTC),
        )
    )
    session.flush()
    session.add_all(
        [
            EmbeddingChunk(**asdict(chunk), repository_id=repository.id, vector=vector)
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
    )
    session.commit()
    logger.info(
        "semantic_index_completed",
        extra={
            "repository_id": repository.id,
            "duration_ms": round((time.monotonic() - start) * 1000),
        },
    )
    return index_status(session, repository, settings)


def retrieve_context(
    session: Session,
    repository: Repository,
    question: str,
    settings: Settings,
    provider: AIProvider,
    strategy: str = "hybrid",
) -> RetrievalResponse:
    start = time.monotonic()
    index = session.get(SemanticIndex, repository.id)
    if index is None or index.fingerprint != fingerprint(settings):
        raise DomainError(
            "index_required",
            "Build the semantic index for the configured embedding model first.",
            409,
        )
    embedded = provider.embed([question])
    if len(embedded) != 1:
        raise DomainError(
            "invalid_embedding", "Provider returned an incomplete query embedding.", 502
        )
    query = normalize(embedded[0], index.dimensions)
    rows = list(
        session.scalars(select(EmbeddingChunk).where(EmbeddingChunk.repository_id == repository.id))
    )
    chunks = [
        Chunk(**{key: getattr(row, key) for key in Chunk.__dataclass_fields__}) for row in rows
    ]
    edges = []
    notes = ["Ranking scores are not confidence estimates. Verify claims against source."]
    if strategy == "hybrid":
        try:
            graph = snapshot_graph(session, repository)
        except DomainError as exc:
            if exc.code != "graph_too_large":
                raise
            notes.append("Dependency graph exceeds its limit; expansion was skipped.")
        else:
            edges = [(edge.source, edge.target) for edge in graph.edges]
            if graph.legacy_files:
                notes.append("Legacy import metadata limits expansion; reimport for full coverage.")
            if graph.unresolved:
                notes.append(
                    f"{len(graph.unresolved)} unresolved imports were excluded from expansion."
                )
            notes.extend(graph.notes[:8])
        notes.append(
            "Expansion uses direct imports/importers of the top two seed excerpts; "
            "at most two additional files."
        )
    ranked = retrieve(
        question, chunks, query, {row.id: row.vector for row in rows}, edges, strategy=strategy
    )
    paths = {chunk.file_id: chunk.path for chunk in chunks}
    hits = [
        RetrievalHit(
            id=f"S{i + 1}",
            chunk_id=item.chunk.id,
            file_id=item.chunk.file_id,
            file_path=item.chunk.path,
            symbol=item.chunk.symbol,
            start_line=item.chunk.start_line,
            end_line=item.chunk.end_line,
            source=item.chunk.source,
            semantic_score=item.semantic_score,
            keyword_score=item.keyword_score,
            symbol_score=item.symbol_score,
            fusion_score=item.fusion_score,
            reason=item.reason,
            via_file_id=item.via_file_id,
            via_file_path=paths.get(item.via_file_id),
        )
        for i, item in enumerate(ranked)
    ]
    return RetrievalResponse(
        repository_id=repository.id,
        strategy=strategy,
        version=RETRIEVAL_VERSION,
        candidate_count=len(chunks),
        hits=hits,
        notes=notes,
        duration_ms=round((time.monotonic() - start) * 1000),
    )


def ask(
    session: Session,
    repository: Repository,
    question: str,
    settings: Settings,
    provider: AIProvider,
    strategy: str = "hybrid",
) -> AskResponse:
    start = time.monotonic()
    retrieval = retrieve_context(session, repository, question, settings, provider, strategy)
    citations = [
        Citation(**hit.model_dump(include=set(Citation.model_fields))) for hit in retrieval.hits
    ]
    if not citations:
        raise DomainError(
            "index_empty", "The semantic index is empty. Reimport this repository.", 409
        )
    answer = provider.answer(question, [c.model_dump() for c in citations])
    valid = {citation.id for citation in citations}
    used = {key for claim in answer.claims for key in claim.citation_ids}
    if (
        not used <= valid
        or (answer.status == "answered" and not answer.claims)
        or (answer.status == "insufficient_context" and answer.claims)
    ):
        raise DomainError(
            "invalid_citations",
            "The model returned unsupported source references. Try a narrower question.",
            502,
        )
    duration = round((time.monotonic() - start) * 1000)
    logger.info(
        "repository_question_completed",
        extra={"repository_id": repository.id, "duration_ms": duration, "status": answer.status},
    )
    return AskResponse(
        retrieval=retrieval,
        **answer.model_dump(),
        repository_id=repository.id,
        commit_sha=repository.commit_sha,
        citations=[c for c in citations if c.id in used],
        model=settings.reasoning_model,
        duration_ms=duration,
    )
