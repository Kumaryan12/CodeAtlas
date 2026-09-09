from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

LanguageName = Literal["python", "javascript", "typescript"]


class Symbol(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    kind: Literal["function", "class", "method", "interface", "type"]
    start_line: int
    end_line: int
    parameters: list[str] = Field(default_factory=list)
    parent_id: str | None = None


class ImportReference(BaseModel):
    specifier: str
    kind: Literal[
        "python_import", "python_from", "javascript_import", "javascript_export", "legacy"
    ]
    names: list[str] = Field(default_factory=list)
    line: int | None = None


class ResolutionConfig(BaseModel):
    path: str
    base_url: str | None = None
    paths: dict[str, list[str]] = Field(default_factory=dict)
    warning: str | None = None


class ParsedSource(BaseModel):
    symbols: list[Symbol] = Field(default_factory=list)
    imports: list[str] = Field(default_factory=list)
    import_references: list[ImportReference] = Field(default_factory=list)
    warning: str | None = None


class ScannedFile(BaseModel):
    path: str
    language: LanguageName
    size_bytes: int
    source: str
    parsed: ParsedSource


class ScanResult(BaseModel):
    files: list[ScannedFile] = Field(default_factory=list)
    skipped: dict[str, int] = Field(default_factory=dict)
    total_entries: int = 0
    resolution_configs: list[ResolutionConfig] = Field(default_factory=list)
