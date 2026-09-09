"""Isolated database-backed source overlays. No filesystem or command capabilities."""

import difflib
import hashlib
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select

from codeatlas.core.errors import DomainError
from codeatlas.models.repository import RepositoryFile
from codeatlas.schemas.agent import FileDiff, WorkspaceDiff

MAX_FILE_BYTES = 12_000
MAX_WORKSPACE_BYTES = 60_000
MAX_FILES = 10


def digest(source):
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PathArgs(Empty):
    path: str = Field(min_length=1, max_length=200)

    @field_validator("path")
    @classmethod
    def safe_path(cls, value):
        parts = value.split("/")
        if (
            not re.fullmatch(r"[A-Za-z0-9_.\-/]+", value)
            or any(part in ("", ".", "..") or part.lower() == ".git" for part in parts)
            or not value.endswith((".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"))
        ):
            raise ValueError("Use a relative supported source path")
        return value


class EditArgs(PathArgs):
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    old_text: str = Field(min_length=1, max_length=MAX_FILE_BYTES)
    new_text: str = Field(max_length=MAX_FILE_BYTES)


class CreateArgs(PathArgs):
    content: str = Field(max_length=MAX_FILE_BYTES)


def unified_diff(path, before, after):
    # Split on LF only: Unicode separators inside literals are not source lines.
    def lines(source):
        return [line + "\n" for line in source.split("\n")[:-1]] + (
            [source.split("\n")[-1]] if source and not source.endswith("\n") else []
        )

    header = f"diff --git a/{path} b/{path}\n"
    if before is None:
        header += "new file mode 100644\n"
    result = list(
        difflib.unified_diff(
            lines(before or ""),
            lines(after),
            fromfile="/dev/null" if before is None else f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    return header + "".join(
        line if line.endswith("\n") else line + "\n\\ No newline at end of file\n"
        for line in result
    )


class DraftWorkspace:
    def __init__(self, session, run, repository):
        self.session, self.run, self.repository = session, run, repository
        self.inspected = {}
        self.reviewed_changes = None

    def original(self, path):
        return self.session.scalar(
            select(RepositoryFile.source).where(
                RepositoryFile.repository_id == self.run.repository_id, RepositoryFile.path == path
            )
        )

    def current(self, path):
        source = self.run.changes.get(path, self.original(path))
        if source is None:
            raise DomainError(
                "workspace_file_not_found", "Source path is absent from this workspace.", 404
            )
        return source

    def execute(self, action, arguments):
        registry = {
            "read_workspace": (PathArgs, self.read),
            "edit_file": (EditArgs, self.edit),
            "create_file": (CreateArgs, self.create),
            "view_diff": (Empty, lambda _: self.diff().model_dump()),
        }
        if self.run.mode != "edit" or action not in registry:
            raise DomainError("tool_not_allowed", "This workspace action is not allowed.", 422)
        schema, function = registry[action]
        try:
            args = schema.model_validate(arguments)
        except ValidationError as exc:
            raise DomainError(
                "invalid_tool_arguments", "Invalid workspace tool arguments.", 422
            ) from exc
        return function(args)

    def read(self, args):
        source = self.current(args.path)
        if len(source.encode()) > MAX_FILE_BYTES:
            raise DomainError(
                "workspace_file_limit", "Workspace files are limited to 12000 UTF-8 bytes.", 422
            )
        sha = digest(source)
        self.inspected[args.path] = sha
        return {"path": args.path, "content": source, "sha256": sha, "version": "draft"}

    def save(self, path, source):
        if "\x00" in source or len(source.encode()) > MAX_FILE_BYTES:
            raise DomainError(
                "workspace_file_limit", "Use text without NUL, up to 12000 UTF-8 bytes.", 422
            )
        changes = {**self.run.changes, path: source}
        if source == self.original(path):
            del changes[path]
        if (
            len(changes) > MAX_FILES
            or sum(len(s.encode()) for s in changes.values()) > MAX_WORKSPACE_BYTES
        ):
            raise DomainError(
                "workspace_limit", "Drafts are limited to 10 files and 60000 UTF-8 bytes.", 422
            )
        self.run.changes = changes
        # Runner commits changes together with the completed tool trace.
        return {"path": path, "sha256": digest(source), "changed_files": len(changes)}

    def edit(self, args):
        source = self.current(args.path)
        sha = digest(source)
        if self.inspected.get(args.path) != sha or args.expected_sha256 != sha:
            raise DomainError(
                "stale_workspace_read", "Read the current workspace file before editing it.", 409
            )
        if source.count(args.old_text) != 1:
            raise DomainError(
                "ambiguous_edit", "old_text must match exactly once in the current file.", 422
            )
        return self.save(args.path, source.replace(args.old_text, args.new_text, 1))

    def create(self, args):
        if args.path in self.run.changes or self.original(args.path) is not None:
            raise DomainError(
                "workspace_file_exists", "This source path already exists. Read and edit it.", 409
            )
        # Reject file/directory and case collisions, including unchanged source files.
        paths = set(self.run.changes) | set(
            self.session.scalars(
                select(RepositoryFile.path).where(
                    RepositoryFile.repository_id == self.run.repository_id
                )
            )
        )
        path = args.path.casefold()
        if any(
            path == p.casefold()
            or path.startswith(p.casefold() + "/")
            or p.casefold().startswith(path + "/")
            for p in paths
        ):
            raise DomainError(
                "workspace_path_conflict", "This path conflicts with an existing source path.", 409
            )
        return self.save(args.path, args.content)

    def diff(self):
        files = []
        for path, source in sorted(self.run.changes.items()):
            original = self.original(path)
            files.append(
                FileDiff(
                    path=path,
                    status="added" if original is None else "modified",
                    diff=unified_diff(path, original, source),
                )
            )
        self.reviewed_changes = dict(self.run.changes)
        return WorkspaceDiff(
            run_id=self.run.id, commit_sha=self.repository.commit_sha, files=files, total=len(files)
        )
