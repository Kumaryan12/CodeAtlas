"""Only snapshot reads are available. No filesystem, shell, URL, or mutation tool."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, load_only

from codeatlas.core.errors import DomainError
from codeatlas.models.repository import CodeSymbol, RepositoryFile
from codeatlas.schemas.qa import Citation
from codeatlas.services.dependency_graph import snapshot_graph
from codeatlas.services.qa import retrieve_context

MAX_EVIDENCE_BYTES = 24_000


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ListFiles(Arguments):
    prefix: str = Field(default="", max_length=200)
    offset: int = Field(default=0, ge=0, le=10000)


class SearchCode(Arguments):
    query: str = Field(min_length=1, max_length=500)


class FileId(Arguments):
    file_id: str

    @model_validator(mode="after")
    def uuid(self):
        UUID(self.file_id)
        return self


class ReadFile(FileId):
    start_line: int = Field(ge=1, le=500000)
    end_line: int = Field(ge=1, le=500000)

    @model_validator(mode="after")
    def range(self):
        if not 0 <= self.end_line - self.start_line < 120:
            raise ValueError("Read range exceeds 120 lines")
        return self


class ReadTools:
    def __init__(self, session: Session, repository, settings, provider):
        self.session, self.repository = session, repository
        self.settings, self.provider = settings, provider
        self.evidence: dict[str, Citation] = {}
        self.graph = None

    def file(self, file_id: str):
        file = self.session.scalar(
            select(RepositoryFile).where(
                RepositoryFile.id == str(UUID(file_id)),
                RepositoryFile.repository_id == self.repository.id,
            )
        )
        if file is None:
            raise DomainError("file_not_found", "File was not found in this snapshot.", 404)
        return file

    def remember(self, citation: Citation):
        for old in self.evidence.values():
            if (old.file_id, old.start_line, old.end_line) == (
                citation.file_id,
                citation.start_line,
                citation.end_line,
            ):
                return old
        size = sum(len(item.source.encode()) for item in self.evidence.values())
        if len(self.evidence) >= 12 or size + len(citation.source.encode()) > MAX_EVIDENCE_BYTES:
            raise DomainError(
                "evidence_limit", "Evidence budget reached. Finish using inspected excerpts.", 422
            )
        citation = citation.model_copy(update={"id": f"E{len(self.evidence) + 1}"})
        self.evidence[citation.id] = citation
        return citation

    def execute(self, action: str, arguments: dict) -> dict:
        registry = {
            "list_files": (ListFiles, self.list_files),
            "search_code": (SearchCode, self.search_code),
            "find_symbol": (SearchCode, self.find_symbol),
            "read_file": (ReadFile, self.read_file),
            "inspect_dependencies": (FileId, self.inspect_dependencies),
        }
        if action not in registry:
            raise DomainError(
                "tool_not_allowed", "Only registered snapshot read tools are allowed.", 422
            )
        schema, handler = registry[action]
        try:
            parsed = schema.model_validate(arguments)
        except (ValueError, ValidationError) as exc:
            raise DomainError(
                "invalid_tool_arguments", "Invalid arguments for the selected read tool.", 422
            ) from exc
        return handler(parsed)

    def list_files(self, args: ListFiles):
        conditions = [
            RepositoryFile.repository_id == self.repository.id,
            RepositoryFile.path.startswith(args.prefix, autoescape=True),
        ]
        files = self.session.scalars(
            select(RepositoryFile)
            .options(load_only(RepositoryFile.id, RepositoryFile.path, raiseload=True))
            .where(*conditions)
            .order_by(RepositoryFile.path)
            .offset(args.offset)
            .limit(20)
        )
        total = self.session.scalar(
            select(func.count()).select_from(RepositoryFile).where(*conditions)
        )
        return {
            "files": [{"file_id": file.id, "path": file.path[:200]} for file in files],
            "total": total,
            "offset": args.offset,
            "page_size": 20,
        }

    def search_code(self, args: SearchCode):
        result = retrieve_context(
            self.session, self.repository, args.query, self.settings, self.provider
        )
        matches = []
        for hit in result.hits[:2]:
            citation = self.remember(Citation(**hit.model_dump(include=set(Citation.model_fields))))
            matches.append(citation.model_dump(exclude={"source"}))
        return {"matches": matches, "notes": result.notes, "limit": 2}

    def find_symbol(self, args: SearchCode):
        conditions = [
            RepositoryFile.repository_id == self.repository.id,
            CodeSymbol.name == args.query,
        ]
        rows = self.session.execute(
            select(CodeSymbol, RepositoryFile)
            .join(RepositoryFile)
            .options(load_only(RepositoryFile.id, RepositoryFile.path, raiseload=True))
            .where(*conditions)
            .order_by(RepositoryFile.path, CodeSymbol.start_line, CodeSymbol.id)
            .limit(20)
        )
        total = self.session.scalar(
            select(func.count()).select_from(CodeSymbol).join(RepositoryFile).where(*conditions)
        )
        return {
            "symbols": [
                {
                    "file_id": file.id,
                    "path": file.path[:200],
                    "name": symbol.name[:200],
                    "kind": symbol.kind,
                    "start_line": symbol.start_line,
                    "end_line": symbol.end_line,
                }
                for symbol, file in rows
            ],
            "total": total,
            "limit": 20,
        }

    def read_file(self, args: ReadFile):
        file = self.file(args.file_id)
        lines = [line.removesuffix("\r") for line in file.source.split("\n")]
        if args.start_line > len(lines):
            raise DomainError(
                "invalid_line_range", "Requested start line is outside the file.", 422
            )
        end = min(args.end_line, len(lines))
        selected, size = [], 0
        for line in lines[args.start_line - 1 : end]:
            if size + len(line.encode()) + 1 > 6000:
                break
            selected.append(line)
            size += len(line.encode()) + 1
        if not selected:
            raise DomainError(
                "source_line_too_large", "This line exceeds the excerpt size limit.", 422
            )
        citation = self.remember(
            Citation(
                id="",
                file_id=file.id,
                file_path=file.path,
                symbol=None,
                start_line=args.start_line,
                end_line=args.start_line + len(selected) - 1,
                source="\n".join(selected),
            )
        )
        return {
            "excerpt": citation.model_dump(exclude={"source"}),
            "total_lines": len(lines),
            "truncated": citation.end_line < end,
            "warning": file.warning,
        }

    def inspect_dependencies(self, args: FileId):
        file = self.file(args.file_id)
        if self.graph is None:
            self.graph = snapshot_graph(self.session, self.repository)
        paths = {node.id: node.file for node in self.graph.nodes}
        imports = [edge.target for edge in self.graph.edges if edge.source == file.id]
        importers = [edge.source for edge in self.graph.edges if edge.target == file.id]

        def items(ids):
            return [{"file_id": key, "path": paths[key][:200]} for key in ids[:10]]

        return {
            "file_id": file.id,
            "imports": items(imports),
            "imported_by": items(importers),
            "import_count": len(imports),
            "importer_count": len(importers),
            "unresolved_count": sum(row.source == file.id for row in self.graph.unresolved),
            "notes": self.graph.notes[:4],
        }
