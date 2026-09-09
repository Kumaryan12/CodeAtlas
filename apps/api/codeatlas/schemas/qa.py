from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: Literal["semantic", "hybrid"] = "hybrid"
    question: str = Field(min_length=1, max_length=1500)

    @field_validator("question")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Question is blank")
        return value.strip()


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=3000)
    citation_ids: list[str] = Field(min_length=1, max_length=6)


class ModelAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["answered", "insufficient_context"]
    claims: list[Claim] = Field(max_length=8)


class Citation(BaseModel):
    id: str
    file_id: str
    file_path: str
    symbol: str | None
    start_line: int
    end_line: int
    source: str


class RetrievalHit(Citation):
    chunk_id: str
    semantic_score: float | None
    keyword_score: float
    symbol_score: float
    fusion_score: float
    reason: Literal["semantic", "hybrid", "dependency"]
    via_file_id: str | None
    via_file_path: str | None


class RetrievalResponse(BaseModel):
    repository_id: str
    strategy: Literal["semantic", "hybrid"]
    version: str
    candidate_count: int
    duration_ms: int
    hits: list[RetrievalHit]
    notes: list[str]


class AskResponse(ModelAnswer):
    retrieval: RetrievalResponse
    repository_id: str
    commit_sha: str | None
    citations: list[Citation]
    model: str
    duration_ms: int


class IndexStatus(BaseModel):
    status: Literal["not_indexed", "ready", "stale"]
    configured: bool
    provider: str
    embedding_model: str
    answer_model: str
    chunk_count: int
    skipped_long_lines: int
    indexed_at: str | None
