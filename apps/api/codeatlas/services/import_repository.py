import logging
import tempfile
import time
from collections import Counter
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import insert, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from codeatlas.core.config import Settings
from codeatlas.core.errors import DomainError
from codeatlas.ingestion.archive import ScanLimits
from codeatlas.ingestion.github import GitHubClient, parse_github_url
from codeatlas.ingestion.runner import analyze
from codeatlas.models.repository import CodeSymbol, Repository, RepositoryFile

logger = logging.getLogger("codeatlas.ingestion")


def import_repository(session: Session, url: str, settings: Settings) -> Repository:
    address = parse_github_url(url)
    repository = Repository(url=address.url, full_name=address.full_name)
    session.add(repository)
    session.commit()
    repository_id = repository.id
    started = time.monotonic()
    try:
        settings.workspace_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(
            prefix=f"{repository.id}-", dir=settings.workspace_root
        ) as directory:
            workspace = Path(directory)
            with httpx.Client(
                follow_redirects=False,
                trust_env=False,
                timeout=10,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Accept-Encoding": "identity",
                    "User-Agent": "CodeAtlas/0.2",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            ) as client:
                snapshot = GitHubClient(
                    client, settings.max_download_bytes, settings.download_timeout_seconds
                ).download(address, workspace)
            result = analyze(workspace, ScanLimits(), settings.analysis_timeout_seconds)
        repository.branch = snapshot.branch
        repository.commit_sha = snapshot.commit_sha
        repository.description = snapshot.description
        repository.file_count = len(result.files)
        repository.symbol_count = sum(len(file.parsed.symbols) for file in result.files)
        repository.source_bytes = sum(file.size_bytes for file in result.files)
        repository.warning_count = sum(file.parsed.warning is not None for file in result.files)
        repository.languages = dict(Counter(file.language for file in result.files))
        repository.skipped = result.skipped
        repository.resolution_configs = [
            config.model_dump() for config in result.resolution_configs
        ]
        repository.status = "partial" if repository.warning_count else "ready"
        file_rows = []
        symbol_rows = []
        for file in result.files:
            file_id = str(uuid4())
            file_rows.append(
                {
                    "id": file_id,
                    "repository_id": repository.id,
                    "path": file.path,
                    "language": file.language,
                    "size_bytes": file.size_bytes,
                    "source": file.source,
                    "warning": file.parsed.warning,
                    "imports": file.parsed.imports,
                    "import_references": [
                        ref.model_dump() for ref in file.parsed.import_references
                    ],
                    "symbol_count": len(file.parsed.symbols),
                }
            )
            # Preserve parent-first traversal order for the symbol self-reference.
            symbol_rows.extend(
                {"file_id": file_id, **symbol.model_dump()} for symbol in file.parsed.symbols
            )
        if file_rows:
            session.execute(insert(RepositoryFile), file_rows)
        if symbol_rows:
            session.execute(insert(CodeSymbol), symbol_rows)
        session.commit()
        logger.info(
            "repository_imported",
            extra={
                "repository_id": repository.id,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "status": repository.status,
            },
        )
        return repository
    except DomainError as exc:
        session.rollback()
        repository.status = "failed"
        repository.error_code = exc.code
        repository.error_message = exc.message
        session.commit()
        logger.warning(
            "repository_import_failed", extra={"repository_id": repository.id, "code": exc.code}
        )
        raise
    except OSError as exc:
        session.rollback()
        repository.status = "failed"
        repository.error_code = "workspace_unavailable"
        repository.error_message = "Cannot create or process the temporary repository workspace."
        session.commit()
        raise DomainError(repository.error_code, repository.error_message, 503) from exc

    except SQLAlchemyError:
        session.rollback()
        try:
            session.execute(
                update(Repository)
                .where(Repository.id == repository_id)
                .values(
                    status="failed",
                    error_code="database_unavailable",
                    error_message="Database write failed. Import the repository again.",
                )
            )
            session.commit()
        except SQLAlchemyError:
            session.rollback()
        raise
