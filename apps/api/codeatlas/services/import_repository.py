import logging
import tempfile
import time
from collections import Counter
from pathlib import Path

import httpx
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
        repository.status = "partial" if repository.warning_count else "ready"
        for file in result.files:
            record = RepositoryFile(
                repository_id=repository.id,
                path=file.path,
                language=file.language,
                size_bytes=file.size_bytes,
                source=file.source,
                warning=file.parsed.warning,
                imports=file.parsed.imports,
                symbol_count=len(file.parsed.symbols),
            )
            session.add(record)
            session.flush()
            # Symbols arrive parent-first. Insert parents before self-FK dependents.
            for symbol in file.parsed.symbols:
                session.add(CodeSymbol(file_id=record.id, **symbol.model_dump()))
            session.flush()
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
