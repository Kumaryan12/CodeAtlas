from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from codeatlas.core.config import Settings
from codeatlas.main import create_app


@pytest.fixture
def client():
    with (
        patch("codeatlas.main.create_database_engine") as engine_factory,
        patch("codeatlas.main.recover_interrupted"),
    ):
        with TestClient(create_app(Settings(_env_file=None))) as test_client:
            yield test_client
        engine_factory.return_value.dispose.assert_called_once()


def test_liveness_does_not_access_database(client):
    with patch("codeatlas.api.health.check_database") as check:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "codeatlas-api"}
    check.assert_not_called()


def test_readiness_checks_database(client):
    with patch("codeatlas.api.health.check_database") as check:
        response = client.get("/api/ready")
    check.assert_called_once()
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}


def test_database_failure_is_sanitized(client, caplog):
    failure = OperationalError("SELECT 1", {}, Exception("secret-password"))
    with patch("codeatlas.api.health.check_database", side_effect=failure):
        response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "secret-password" not in response.text + caplog.text


def test_unknown_route(client):
    assert client.get("/api/missing").status_code == 404


def test_settings_respect_environment(monkeypatch):
    monkeypatch.setenv("CODEATLAS_DATABASE_URL", "postgresql+psycopg://user:secret@localhost/db")
    settings = Settings(_env_file=None)
    assert settings.database_url.get_secret_value().endswith("/db")
    assert "secret" not in repr(settings)
