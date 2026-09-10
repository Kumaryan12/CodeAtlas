"""Fixed application-owned MCP names and strict response contracts."""

from typing import Literal

from pydantic import Field

from codeatlas.agents.tools import Arguments, FileId, ListFiles, ReadFile, SearchCode
from codeatlas.schemas.qa import Citation

TOOLS = {
    "list_files": ListFiles,
    "find_symbol": SearchCode,
    "read_file": ReadFile,
    "inspect_dependencies": FileId,
}
PREFIX = "codeatlas_"
MAX_RESULT_BYTES = 32_000


class FileItem(Arguments):
    file_id: str
    path: str = Field(max_length=200)


class FilesResult(Arguments):
    files: list[FileItem] = Field(max_length=20)
    total: int = Field(ge=0)
    offset: int = Field(ge=0, le=10000)
    page_size: Literal[20]


class SymbolItem(FileItem):
    name: str = Field(max_length=200)
    kind: str = Field(max_length=100)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)


class SymbolsResult(Arguments):
    symbols: list[SymbolItem] = Field(max_length=20)
    total: int = Field(ge=0)
    limit: Literal[20]


class ReadResult(Arguments):
    excerpt: dict
    total_lines: int = Field(ge=1)
    truncated: bool
    warning: str | None


class DependenciesResult(Arguments):
    file_id: str
    imports: list[FileItem] = Field(max_length=10)
    imported_by: list[FileItem] = Field(max_length=10)
    import_count: int = Field(ge=0)
    importer_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    notes: list[str] = Field(max_length=4)


RESULTS = {
    "list_files": FilesResult,
    "find_symbol": SymbolsResult,
    "read_file": ReadResult,
    "inspect_dependencies": DependenciesResult,
}


class ToolFailure(Arguments):
    code: str = Field(max_length=100)
    message: str = Field(max_length=300)


class Envelope(Arguments):
    repository_id: str
    result: dict | None = None
    evidence: list[Citation] = Field(default_factory=list, max_length=1)
    error: ToolFailure | None = None
