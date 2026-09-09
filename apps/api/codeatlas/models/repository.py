from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    url: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    branch: Mapped[str | None] = mapped_column(String(255))
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="importing")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    symbol_count: Mapped[int] = mapped_column(Integer, default=0)
    source_bytes: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    languages: Mapped[dict] = mapped_column(JSON, default=dict)
    skipped: Mapped[dict] = mapped_column(JSON, default=dict)
    resolution_configs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("ix_repositories_created_at", "created_at"),)


class RepositoryFile(Base):
    __tablename__ = "repository_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    repository_id: Mapped[str] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"))
    path: Mapped[str] = mapped_column(String(1000))
    language: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(Text)
    imports: Mapped[list] = mapped_column(JSON, default=list)
    import_references: Mapped[list | None] = mapped_column(JSON, nullable=True)
    warning: Mapped[str | None] = mapped_column(Text)
    symbol_count: Mapped[int] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("repository_id", "path", name="uq_file_repository_path"),)


class CodeSymbol(Base):
    __tablename__ = "code_symbols"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("repository_files.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("code_symbols.id", ondelete="CASCADE"))
    parameters: Mapped[list] = mapped_column(JSON, default=list)

    __table_args__ = (Index("ix_code_symbols_file_id", "file_id"),)
