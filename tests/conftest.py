"""Offline test guardrails; live manual examples are outside test discovery."""

import socket
from collections.abc import Iterator
from typing import NoReturn

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def is_integration_test(request: pytest.FixtureRequest) -> bool:
    """Integration tests are explicitly marked and need a real database."""
    return request.node.get_closest_marker("integration") is not None


@pytest.fixture(autouse=True)
def block_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unit tests must not contact providers or a running server.

    Tests marked `integration` opt out: they require a real, isolated
    PostgreSQL database (see tests/integration and TEST_DATABASE_URL).
    """
    if is_integration_test(request):
        return

    def reject(*args: object, **kwargs: object) -> NoReturn:
        raise AssertionError("Network access is forbidden in the offline test suite")

    monkeypatch.setattr(socket.socket, "connect", reject)
    monkeypatch.setattr(socket.socket, "connect_ex", reject)
    monkeypatch.setattr(socket, "getaddrinfo", reject)


@pytest.fixture
def registry(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[tuple]:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/unused")
    # Never write generated artifacts into the repository's data directory.
    monkeypatch.setenv(
        "ARTIFACT_DIR", str(tmp_path_factory.mktemp("artifacts", numbered=True))
    )
    monkeypatch.setenv("SECRET_KEY", "registry-unit-test-only")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("RUNTIME_PROFILE", "local")
    monkeypatch.setenv("DEPLOYMENT_EXECUTOR", "simulated")
    from core.config import get_settings

    get_settings.cache_clear()
    from core.database import Base, get_db
    from main import create_app
    from models.database import User
    from services.auth_service import create_access_token

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection: object, _: object) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    # Only runtime tables: do not replace or attempt to run pgvector migrations.
    tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name
        in {
            "users",
            "data_catalogs",
            "pipelines",
            "teams",
            "team_memberships",
            "applications",
            "application_roles",
            "audit_events",
            "environments",
            "environment_bindings",
            "operations",
            "operation_attempts",
            "operation_reservations",
            "queue_probes",
            "operation_commands",
            "worker_heartbeats",
            "template_versions",
            "artifacts",
            "deployment_revisions",
            "validation_results",
        }
    ]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as db:
        for identifier in range(1, 7):
            db.add(
                User(
                    id=identifier,
                    email=f"user{identifier}@example.test",
                    username=f"user{identifier}",
                    password_hash="unused",
                    is_active=identifier != 6,
                    is_platform_admin=identifier == 1,
                )
            )
        db.commit()

    def session() -> Iterator[Session]:
        with Session(engine) as db:
            yield db

    app = create_app()
    app.dependency_overrides[get_db] = session
    headers = {
        i: {
            "Authorization": "Bearer "
            + create_access_token({"sub": f"user{i}@example.test"})
        }
        for i in range(1, 7)
    }
    with TestClient(app, raise_server_exceptions=False) as client:
        team = client.post(
            "/api/v1/teams", headers=headers[1], json={"name": "Engineering"}
        )
        assert team.status_code == 201, team.text
        team_id = team.json()["id"]
        assert (
            client.post(
                f"/api/v1/teams/{team_id}/members",
                headers=headers[1],
                json={"user_id": 2},
            ).status_code
            == 201
        )
        yield client, headers, engine, team_id
    engine.dispose()
    get_settings.cache_clear()
