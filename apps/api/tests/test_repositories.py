from unittest.mock import patch
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import event, inspect
from test_archive import make_archive

from codeatlas.core.errors import DomainError
from codeatlas.ingestion.github import Snapshot
from codeatlas.models.repository import Base


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


def test_summary_queries_do_not_load_source_text(api, fake_download):
    repo = api.post("/api/repositories", json={"url": "https://github.com/a/b"}).json()
    statements = []

    @event.listens_for(api.app.state.database, "before_cursor_execute")
    def record_selects(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT"):
            statements.append(statement)

    assert api.get(f"/api/repositories/{repo['id']}/files").status_code == 200
    assert api.get(f"/api/repositories/{repo['id']}/symbols").status_code == 200
    assert statements
    assert all("repository_files.source" not in statement for statement in statements)
    assert all("repository_files.imports" not in statement for statement in statements)


def test_graph_is_scoped_and_does_not_fetch_source(api, fake_download):
    repo = api.post("/api/repositories", json={"url": "https://github.com/a/b"}).json()
    statements = []

    @event.listens_for(api.app.state.database, "before_cursor_execute")
    def record_graph_selects(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT"):
            statements.append(statement)

    response = api.get(f"/api/repositories/{repo['id']}/graph")
    assert response.status_code == 200
    assert len(response.json()["nodes"]) == 3
    assert response.json()["legacy_files"] == 0
    assert all("repository_files.source" not in statement for statement in statements)
    assert api.get(f"/api/repositories/{uuid4()}/graph").status_code == 404


def test_failed_snapshot_has_no_graph(api):
    with patch(
        "codeatlas.services.import_repository.GitHubClient.download",
        side_effect=DomainError("missing", "Missing", 404),
    ):
        api.post("/api/repositories", json={"url": "https://github.com/a/b"})
    repo = api.get("/api/repositories").json()["items"][0]
    assert api.get(f"/api/repositories/{repo['id']}/graph").status_code == 409


def test_persisted_graph_resolves_python_and_captured_aliases(api, monkeypatch):
    def download(self, repository, workspace):
        make_archive(
            workspace / "repository.tar.gz",
            {
                "repo/pkg/__init__.py": b"",
                "repo/pkg/a.py": b"from . import b\ndef run(): pass",
                "repo/pkg/b.py": b"from .a import run",
                "repo/web/tsconfig.json": b'{"compilerOptions":{"paths":{"@/*":["src/*"]}}}',
                "repo/web/src/a.ts": b"import '@/b';",
                "repo/web/src/b.ts": b"export const value = 1;",
            },
        )
        return Snapshot(repository.full_name, repository.url, "main", "b" * 40, None)

    monkeypatch.setattr("codeatlas.services.import_repository.GitHubClient.download", download)
    repo = api.post("/api/repositories", json={"url": "https://github.com/example/graph"}).json()
    graph = api.get(f"/api/repositories/{repo['id']}/graph").json()
    paths = {node["id"]: node["file"] for node in graph["nodes"]}
    pairs = {(paths[edge["source"]], paths[edge["target"]]) for edge in graph["edges"]}
    assert ("web/src/a.ts", "web/src/b.ts") in pairs
    assert ("pkg/a.py", "pkg/b.py") in pairs
    assert ("pkg/b.py", "pkg/a.py") in pairs
    assert len(graph["cycles"]) == 1
    assert {paths[node] for node in graph["cycles"][0]} == {"pkg/a.py", "pkg/b.py"}
    assert not graph["unresolved"]
    assert all(evidence["line"] == 1 for edge in graph["edges"] for evidence in edge["evidence"])
    assert any(
        evidence["resolution"] == "typescript_paths"
        for edge in graph["edges"]
        for evidence in edge["evidence"]
    )


def test_data_flow_view_has_scoped_evidence_and_validates_view(api, monkeypatch):
    def download(self, repository, workspace):
        make_archive(
            workspace / "repository.tar.gz",
            {
                "repo/__init__.py": b"",
                "repo/data.py": b"def load():\n    return [1]\n",
                "repo/model.py": b"def train(rows):\n    return rows\n",
                "repo/main.py": b"from .data import load\n"
                b"from .model import train\ntrain(load())\n",
            },
        )
        return Snapshot(repository.full_name, repository.url, "main", "b" * 40, None)

    monkeypatch.setattr("codeatlas.services.import_repository.GitHubClient.download", download)
    repo = api.post("/api/repositories", json={"url": "https://github.com/example/flow"}).json()
    prefix = f"/api/repositories/{repo['id']}/graph"
    graph = api.get(prefix + "?view=data_flow").json()
    paths = {node["id"]: node["file"] for node in graph["nodes"]}
    assert [(paths[e["source"]], paths[e["target"]]) for e in graph["edges"]] == [
        ("data.py", "model.py")
    ]
    evidence = graph["edges"][0]["evidence"][0]
    assert paths[evidence["context_file_id"]] == evidence["context_file_path"] == "main.py"
    assert evidence["line"] == 3
    assert all(e["relationship"] == "imports" for e in api.get(prefix).json()["edges"])
    assert api.get(prefix + "?view=guessed").status_code == 422
    assert api.get(f"/api/repositories/{uuid4()}/graph?view=data_flow").status_code == 404
