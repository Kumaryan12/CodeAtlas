from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from codeatlas.core.errors import DomainError
from codeatlas.ingestion.github import parse_github_url
from codeatlas.parsers.types import LanguageName, Symbol


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str = Field(max_length=255)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        try:
            return parse_github_url(value).url
        except DomainError as exc:
            raise ValueError(exc.message) from exc


class RepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    url: str
    full_name: str
    branch: str | None
    commit_sha: str | None
    description: str | None
    status: Literal["importing", "ready", "partial", "failed"]
    error_code: str | None
    error_message: str | None
    file_count: int
    symbol_count: int
    source_bytes: int
    warning_count: int
    languages: dict[str, int]
    skipped: dict[str, int]
    created_at: datetime


class RepositoryList(BaseModel):
    items: list[RepositoryResponse]
    total: int


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    repository_id: str
    path: str
    language: LanguageName
    size_bytes: int
    warning: str | None
    symbol_count: int


class FileList(BaseModel):
    items: list[FileResponse]
    total: int


class FileDetail(FileResponse):
    source: str
    imports: list[str]
    symbols: list[Symbol]


class SymbolResponse(Symbol):
    file_id: str
    file_path: str
    language: LanguageName


class SymbolList(BaseModel):
    items: list[SymbolResponse]
    total: int
