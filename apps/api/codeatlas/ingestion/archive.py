import gzip
import tarfile
from collections import Counter
from pathlib import Path, PurePosixPath

from pydantic import BaseModel

from codeatlas.core.errors import DomainError
from codeatlas.dependencies.config import read_resolution_config
from codeatlas.parsers.javascript import parse_javascript
from codeatlas.parsers.python import parse_python
from codeatlas.parsers.types import ScannedFile, ScanResult

IGNORED_DIRECTORIES = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "env",
    ".env",
    "__pycache__",
    ".next",
    ".nuxt",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "vendor",
    ".idea",
    ".vscode",
    ".cache",
    "site-packages",
    ".yarn",
    ".pnpm-store",
}
EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
}


class ScanLimits(BaseModel):
    max_expanded_bytes: int = 100 * 1024 * 1024
    max_entries: int = 10_000
    max_file_bytes: int = 512 * 1024
    max_source_bytes: int = 10 * 1024 * 1024
    max_symbols: int = 20_000
    max_imports: int = 50_000


def safe_member_path(name: str) -> PurePosixPath:
    parts = name.rstrip("/").split("/")
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or len(name) > 1000
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
        or any(part in {"", ".", ".."} or ":" in part for part in parts)
    ):
        raise DomainError("unsafe_archive", "Repository archive contains an unsafe path.")
    return PurePosixPath(*parts)


def scan_archive(archive: Path, workspace: Path, limits: ScanLimits) -> ScanResult:
    """Read only bounded regular source files. No extractall, links, hooks, or imports."""
    expanded = workspace / "expanded.tar"
    total = 0
    try:
        # Bound gzip expansion before tarfile interprets PAX/extended headers.
        with gzip.open(archive, "rb") as compressed, expanded.open("wb") as output:
            while chunk := compressed.read(64 * 1024):
                total += len(chunk)
                if total > limits.max_expanded_bytes:
                    raise DomainError(
                        "repository_too_large", "Expanded archive exceeds the size limit.", 413
                    )
                output.write(chunk)
        return scan_tar(expanded, limits)
    except (tarfile.TarError, OSError, EOFError, UnicodeError, ValueError) as exc:
        raise DomainError(
            "invalid_archive", "Repository archive is malformed or unreadable."
        ) from exc


def scan_tar(archive: Path, limits: ScanLimits) -> ScanResult:
    result = ScanResult()
    skipped: Counter[str] = Counter()
    seen: set[str] = set()
    roots: set[str] = set()
    source_bytes = symbol_count = import_count = config_bytes = 0
    with tarfile.open(archive, mode="r:") as contents:
        for member in contents:
            result.total_entries += 1
            if result.total_entries > limits.max_entries:
                raise DomainError("repository_too_large", "Archive has too many entries.", 413)
            full = safe_member_path(member.name)
            roots.add(full.parts[0])
            if len(roots) > 1 or (len(full.parts) == 1 and not member.isdir()):
                raise DomainError(
                    "unsafe_archive", "Archive must have one repository root directory."
                )
            if (
                member.issym()
                or member.islnk()
                or member.issparse()
                or not (member.isfile() or member.isdir())
            ):
                raise DomainError(
                    "unsafe_archive",
                    "Archives with links, sparse files, or special entries are not supported.",
                )
            if member.isdir():
                continue
            path = PurePosixPath(*full.parts[1:])
            key = str(path)
            if key.casefold() in seen:
                raise DomainError(
                    "unsafe_archive", "Archive contains duplicate or case-colliding paths."
                )
            seen.add(key.casefold())
            reason = None
            language = EXTENSIONS.get(path.suffix.lower())
            if any(part.lower() in IGNORED_DIRECTORIES for part in path.parts[:-1]):
                reason = "ignored_directory"
            elif path.name in {"tsconfig.json", "jsconfig.json"}:
                if member.size > 128 * 1024 or len(result.resolution_configs) >= 64:
                    raise DomainError(
                        "repository_too_large", "Alias configuration exceeds the scan limit.", 413
                    )
                config_bytes += member.size
                if config_bytes > 1024 * 1024:
                    raise DomainError(
                        "repository_too_large", "Alias configuration exceeds 1 MiB.", 413
                    )
                handle = contents.extractfile(member)
                if handle is None:
                    raise DomainError("invalid_archive", "Unable to read configuration.")
                with handle:
                    raw_config = handle.read(128 * 1024 + 1)
                result.resolution_configs.append(
                    read_resolution_config(key, raw_config.decode("utf-8-sig", errors="replace"))
                )
                skipped["resolution_config"] += 1
                continue
            elif not language:
                reason = "unsupported_type"
            elif member.size > limits.max_file_bytes:
                reason = "oversized_file"
            elif path.name.endswith(
                (
                    ".min.js",
                    ".min.ts",
                    ".generated.ts",
                    ".generated.js",
                    "_pb2.py",
                    "_pb2_grpc.py",
                    ".d.ts",
                )
            ):
                reason = "generated_file"
            if reason:
                skipped[reason] += 1
                continue
            handle = contents.extractfile(member)
            if handle is None:
                raise DomainError("invalid_archive", "Unable to read archive entry.")
            with handle:
                raw = handle.read(limits.max_file_bytes + 1)
            if len(raw) != member.size:
                raise DomainError(
                    "invalid_archive", "Archive entry size does not match its header."
                )
            if b"\x00" in raw or any(byte < 9 or 13 < byte < 32 for byte in raw):
                skipped["binary_file"] += 1
                continue
            try:
                source = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                skipped["unsupported_encoding"] += 1
                continue
            header = source[:1000].lower()
            if (
                "@generated" in header
                or "code generated" in header
                or "automatically generated" in header
            ):
                skipped["generated_file"] += 1
                continue
            source_bytes += len(raw)
            if source_bytes > limits.max_source_bytes:
                raise DomainError(
                    "repository_too_large", "Relevant source exceeds the storage limit.", 413
                )
            parsed = (
                parse_python(source)
                if language == "python"
                else parse_javascript(
                    source, typescript=language == "typescript", tsx=path.suffix.lower() == ".tsx"
                )
            )
            symbol_count += len(parsed.symbols)
            import_count += sum(1 + len(ref.names) for ref in parsed.import_references)
            if import_count > limits.max_imports:
                raise DomainError(
                    "repository_too_large", "Repository has too many import statements.", 413
                )
            if symbol_count > limits.max_symbols:
                raise DomainError("repository_too_large", "Repository has too many symbols.", 413)
            result.files.append(
                ScannedFile(
                    path=key,
                    language=language,
                    size_bytes=len(raw),
                    source=source,
                    parsed=parsed,
                )
            )
    result.files.sort(key=lambda item: item.path)
    result.skipped = dict(skipped)
    return result
