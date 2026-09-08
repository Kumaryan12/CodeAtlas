from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.pool import StaticPool
from test_archive import make_archive

from codeatlas.core.config import Settings
from codeatlas.core.errors import DomainError
from codeatlas.ingestion.github import Snapshot
from codeatlas.main import create_app
from codeatlas.models.repository import Base


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


def test_migration_matches_models_and_reverses(migrated_engine):
    engine, config = migrated_engine
    with engine.begin() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names()) == {"alembic_version"}
        command.upgrade(config, "head")
        assert "repository_files" in inspect(connection).get_table_names()


def test_import_persists_files_symbols_and_scoped_access(api, fake_download):
    response = api.post("/api/repositories", json={"url": "https://github.com/example/demo.git"})
    assert response.status_code == 201, response.text
    repo = response.json()
    assert repo["status"] == "partial"
    assert repo["file_count"] == 3
    assert repo["symbol_count"] == 3
    assert repo["languages"] == {"python": 2, "typescript": 1}
    assert repo["skipped"] == {"ignored_directory": 1}
    assert repo["commit_sha"] == "a" * 40
    assert repo["warning_count"] == 1
    prefix = f"/api/repositories/{repo['id']}"
    assert api.get(prefix).json()["full_name"] == "example/demo"
    listed = api.get("/api/repositories").json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == repo["id"]
    files = api.get(prefix + "/files?limit=1").json()
    assert len(files["items"]) == 1
    assert files["total"] == 3
    file = files["items"][0]
    detail = api.get(prefix + f"/files/{file['id']}").json()
    assert detail["source"].startswith("class Auth:")
    login = next(symbol for symbol in detail["symbols"] if symbol["name"] == "login")
    assert login["start_line"] == 2
    assert login["parent_id"] is not None
    symbols = api.get(prefix + f"/symbols?file_id={file['id']}").json()
    assert symbols["total"] == 2
    assert symbols["items"][0]["file_path"] == "auth.py"
    other = api.post("/api/repositories", json={"url": "https://github.com/example/other"}).json()
    assert api.get(f"/api/repositories/{other['id']}/files/{file['id']}").status_code == 404
    assert list(api.app.state.settings.workspace_root.iterdir()) == []


def test_invalid_input_does_not_download(api):
    with patch("codeatlas.services.import_repository.GitHubClient.download") as download:
        response = api.post("/api/repositories", json={"url": "http://localhost/secret"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    download.assert_not_called()
    assert api.get("/api/repositories").json()["total"] == 0


def test_failure_is_persisted_and_workspace_removed(api):
    failure = DomainError("repository_unavailable", "Repository is private or missing.", 404)
    with patch("codeatlas.services.import_repository.GitHubClient.download", side_effect=failure):
        response = api.post("/api/repositories", json={"url": "https://github.com/a/b"})
    assert response.status_code == 404
    repo = api.get("/api/repositories").json()["items"][0]
    assert repo["status"] == "failed"
    assert repo["file_count"] == 0
    assert repo["error_code"] == "repository_unavailable"
    assert list(api.app.state.settings.workspace_root.iterdir()) == []


def test_busy_import_rejected(api):
    api.app.state.import_lock.acquire()
    try:
        response = api.post("/api/repositories", json={"url": "https://github.com/a/b"})
    finally:
        api.app.state.import_lock.release()
    assert response.status_code == 409


@pytest.mark.parametrize(
    "path",
    ["/api/repositories/not-a-uuid", "/api/repositories?limit=0", "/api/repositories?offset=-1"],
)
def test_malformed_identifiers_and_pagination(api, path):
    assert api.get(path).status_code == 422


def test_unknown_snapshot(api):
    assert api.get(f"/api/repositories/{uuid4()}").status_code == 404


def test_large_json_body_rejected_before_validation(api):
    response = api.post("/api/repositories", json={"url": "x" * 5000})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_database_failure_rolls_back_all_files(api, fake_download):
    from sqlalchemy.exc import OperationalError

    engine = api.app.state.database
    failed = False

    @event.listens_for(engine, "before_cursor_execute")
    def fail_symbol_write(connection, cursor, statement, parameters, context, executemany):
        nonlocal failed
        if not failed and statement.startswith("INSERT INTO code_symbols"):
            failed = True
            raise OperationalError(statement, {}, Exception("private database details"))

    response = api.post("/api/repositories", json={"url": "https://github.com/a/b"})
    assert response.status_code == 503
    assert "private database details" not in response.text
    repo = api.get("/api/repositories").json()["items"][0]
    assert repo["status"] == "failed"
    assert repo["file_count"] == 0
    assert api.get(f"/api/repositories/{repo['id']}/files").json()["items"] == []
