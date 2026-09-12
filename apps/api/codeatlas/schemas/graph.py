from typing import Literal

from pydantic import BaseModel, Field

from codeatlas.parsers.types import ImportReference, LanguageName


class GraphFile(BaseModel):
    id: str
    path: str
    language: LanguageName
    symbol_count: int = 0
    warning: str | None = None
    imports: list[str] = Field(default_factory=list)
    import_references: list[ImportReference] | None = None


class GraphNode(BaseModel):
    id: str
    label: str
    type: Literal["file"] = "file"
    file: str
    language: LanguageName
    symbol_count: int
    warning: str | None


class EdgeEvidence(BaseModel):
    specifier: str
    line: int | None
    kind: str
    resolution: str
    context_file_id: str | None = None
    context_file_path: str | None = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relationship: Literal["imports", "data_flow"] = "imports"
    evidence: list[EdgeEvidence] = Field(default_factory=list)
    in_cycle: bool = False


class UnresolvedImport(BaseModel):
    source: str
    specifier: str
    line: int | None
    reason: str
    candidates: list[str] = Field(default_factory=list)


class DependencyGraph(BaseModel):
    repository_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    unresolved: list[UnresolvedImport]
    cycles: list[list[str]]
    notes: list[str]
    legacy_files: int
