"""Symbol-first chunks with exact source ranges and bounded line-based splitting."""

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from codeatlas.models.repository import CodeSymbol, RepositoryFile

CHUNK_VERSION = "symbols-v1"
MAX_CHUNK_BYTES = 6000
MAX_CHUNKS = 2000
MAX_INDEX_BYTES = 2_000_000


@dataclass(frozen=True)
class Chunk:
    id: str
    file_id: str
    path: str
    language: str
    symbol: str | None
    kind: str
    start_line: int
    end_line: int
    source: str

    def embedding_text(self) -> str:
        header = f"{self.path} | {self.language} | {self.kind} {(self.symbol or '')[:200]}"
        header = header.encode("utf-8")[:1000].decode("utf-8", errors="ignore")
        return f"{header}\n{self.source}"


def chunk_file(file: RepositoryFile, symbols: list[CodeSymbol]) -> tuple[list[Chunk], int]:
    lines = file.source.splitlines()
    covered: set[int] = set()
    ranges = []
    # Prefer innermost symbols: enclosing classes/functions contribute only their
    # uncovered declarations and body. Every source line is embedded at most once.
    for symbol in sorted(symbols, key=lambda s: (s.end_line - s.start_line, s.start_line, s.id)):
        start, end = max(1, symbol.start_line), min(len(lines), symbol.end_line)
        available = [n for n in range(start, end + 1) if n not in covered]
        covered.update(available)
        ranges.append((available, symbol.name, symbol.kind))
    ranges.append(([n for n in range(1, len(lines) + 1) if n not in covered], None, "module"))
    chunks: list[Chunk] = []
    skipped = 0
    for numbers, symbol, kind in ranges:
        group: list[int] = []
        size = 0

        def emit(group, symbol=symbol, kind=kind):
            if not group:
                return
            source = "\n".join(lines[n - 1] for n in group)
            if not source.strip():
                return
            start, end = group[0], group[-1]
            chunks.append(
                Chunk(
                    str(uuid5(NAMESPACE_URL, f"{CHUNK_VERSION}:{file.id}:{start}:{end}")),
                    file.id,
                    file.path,
                    file.language,
                    symbol[:200] if symbol else None,
                    kind,
                    start,
                    end,
                    source,
                )
            )

        for number in numbers:
            line_size = len(lines[number - 1].encode("utf-8")) + 1
            if group and (number != group[-1] + 1 or size + line_size > MAX_CHUNK_BYTES):
                emit(group)
                group = []
                size = 0
            if line_size > MAX_CHUNK_BYTES:
                skipped += 1
                continue
            group.append(number)
            size += line_size
        emit(group)
    return sorted(chunks, key=lambda c: c.start_line), skipped
