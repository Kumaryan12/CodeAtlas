from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from test_archive import make_archive

from codeatlas.core.config import Settings
from codeatlas.ingestion.github import Snapshot
from codeatlas.main import create_app


@pytest.fixture
def migrated_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield engine, config
    engine.dispose()


@pytest.fixture
def api(migrated_engine, tmp_path):
    engine, _ = migrated_engine
    settings = Settings(_env_file=None, workspace_root=tmp_path / "workspaces")
    with patch("codeatlas.main.create_database_engine", return_value=engine):
        with TestClient(create_app(settings)) as client:
            yield client


@pytest.fixture
def fake_download(monkeypatch):
    def download(self, repository, workspace):
        make_archive(
            workspace / "repository.tar.gz",
            {
                "repo/auth.py": b"class Auth:\n    def login(self, email):\n        return email\n",
                "repo/client.ts": b"export const login = (email: string) => email;",
                "repo/broken.py": b"def broken(:",
                "repo/node_modules/a.js": b"ignored",
            },
        )
        return Snapshot(repository.full_name, repository.url, "main", "a" * 40, "Fixture repo")

    monkeypatch.setattr("codeatlas.services.import_repository.GitHubClient.download", download)
