"""Isolated PostgreSQL integration tests for the Alembic migration chain.

Require a real, pgvector-capable PostgreSQL reachable via TEST_DATABASE_URL.
Never run against a developer's primary or shared database: each test runs
inside a uniquely named, disposable schema that is dropped afterward. Skipped
with a visible reason when TEST_DATABASE_URL is unset.
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2] / "backend"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

EXPECTED_HEAD_TABLES = {
    "users",
    "data_catalogs",
    "models",
    "pipelines",
    "document_chunks",
    "conversations",
    "messages",
    "background_jobs",
    "teams",
    "team_memberships",
    "applications",
    "application_roles",
    "audit_events",
}
HEAD_REVISION = "005_owned_applications"


def _scoped_database_url(schema: str) -> str:
    """Same database as TEST_DATABASE_URL, scoped to an isolated schema."""
    assert TEST_DATABASE_URL is not None
    url = make_url(TEST_DATABASE_URL)
    query = {**url.query, "options": f"-c search_path={schema},public"}
    return url.set(query=query).render_as_string(hide_password=False)


def _alembic_config() -> Config:
    """backend/alembic/env.py derives sqlalchemy.url from Settings.database_url,
    which reads the DATABASE_URL environment variable set by isolated_schema."""
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return config


@pytest.fixture
def isolated_schema(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A uniquely named, disposable schema; dropped after the test regardless.

    Also points the application's DATABASE_URL/SECRET_KEY settings at it, since
    backend/alembic/env.py derives the migration URL from Settings rather than
    from the Alembic Config object directly.
    """
    if not TEST_DATABASE_URL:
        pytest.skip(
            "TEST_DATABASE_URL is not set; isolated PostgreSQL migration "
            "integration tests are skipped. Point it at a dedicated, "
            "disposable pgvector-capable PostgreSQL database."
        )
    schema = f"t01b_test_{uuid.uuid4().hex[:12]}"
    engine = sa.create_engine(TEST_DATABASE_URL)
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))

        from core.config import get_settings

        monkeypatch.setenv("DATABASE_URL", _scoped_database_url(schema))
        monkeypatch.setenv("SECRET_KEY", "integration-test-secret-key-only")
        monkeypatch.setenv("DEBUG", "false")
        get_settings.cache_clear()

        yield schema
    finally:
        try:
            from core.config import get_settings as _get_settings

            _get_settings.cache_clear()
        except ImportError:
            pass
        with engine.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_pgvector_extension_is_available(isolated_schema: str) -> None:
    engine = sa.create_engine(_scoped_database_url(isolated_schema))
    try:
        with engine.connect() as conn:
            available = conn.execute(
                sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
            ).first()
    finally:
        engine.dispose()
    assert available is not None, (
        "pgvector extension is not available on this PostgreSQL server; "
        "use a pgvector-capable image (e.g. pgvector/pgvector)"
    )


def test_migrations_reach_head_with_expected_tables(isolated_schema: str) -> None:
    command.upgrade(_alembic_config(), "head")

    engine = sa.create_engine(_scoped_database_url(isolated_schema))
    try:
        inspector = sa.inspect(engine)
        tables = set(inspector.get_table_names(schema=isolated_schema))
        assert EXPECTED_HEAD_TABLES <= tables
        with engine.connect() as conn:
            head = conn.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        assert head == HEAD_REVISION
    finally:
        engine.dispose()


def test_upgrade_preserves_data_from_an_earlier_revision(isolated_schema: str) -> None:
    config = _alembic_config()
    command.upgrade(config, "001_initial")

    engine = sa.create_engine(_scoped_database_url(isolated_schema))
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO users (email, username, password_hash) "
                    "VALUES (:email, :username, :password_hash)"
                ),
                {
                    "email": "disposable@example.test",
                    "username": "disposable",
                    "password_hash": "not-a-real-hash",
                },
            )

        command.upgrade(config, "head")

        with engine.connect() as conn:
            preserved_username = conn.execute(
                sa.text("SELECT username FROM users WHERE email = :email"),
                {"email": "disposable@example.test"},
            ).scalar_one()
        assert preserved_username == "disposable"
    finally:
        engine.dispose()


def test_upgrade_from_old_head_preserves_user_and_safe_flags(
    isolated_schema: str,
) -> None:
    config = _alembic_config()
    command.upgrade(config, "004_add_background_jobs")
    engine = sa.create_engine(_scoped_database_url(isolated_schema))
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO users (email, username, password_hash) VALUES ('legacy@example.test', 'legacy', 'preserved-hash')"
                )
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            row = connection.execute(
                sa.text(
                    "SELECT username, password_hash, is_active, is_platform_admin FROM users"
                )
            ).one()
            assert tuple(row) == ("legacy", "preserved-hash", True, False)
        # Compare new runtime metadata against the real migrated schema.
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
        from core.database import Base

        new_tables = {
            "teams",
            "team_memberships",
            "applications",
            "application_roles",
            "audit_events",
        }
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection,
                opts={
                    "include_object": lambda obj, name, kind, reflected, compare_to: (
                        name in new_tables
                        if kind == "table"
                        else obj.table.name in new_tables
                    )
                },
            )
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()


@pytest.fixture
def registry_engine(isolated_schema: str) -> Iterator[sa.Engine]:
    command.upgrade(_alembic_config(), "head")
    engine = sa.create_engine(_scoped_database_url(isolated_schema))
    from models.database import User
    from models.platform import Team, TeamMembership
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        db.add_all(
            [
                User(
                    id=i,
                    email=f"pg{i}@example.test",
                    username=f"pg{i}",
                    password_hash="unused",
                    is_platform_admin=i == 1,
                )
                for i in (1, 2, 3)
            ]
        )
        db.flush()
        team = Team(name="Postgres team")
        db.add(team)
        db.flush()
        db.add(TeamMembership(team_id=team.id, user_id=2))
        db.commit()
    try:
        yield engine
    finally:
        engine.dispose()


def test_postgres_api_transaction_and_constraint_failures(
    registry_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.database import get_db
    from fastapi.testclient import TestClient
    from main import create_app
    from models.platform import Application, ApplicationRole, AuditEvent, Team
    from services import audit_service
    from services.auth_service import create_access_token
    from sqlalchemy.orm import Session

    def session() -> Iterator[Session]:
        with Session(registry_engine) as db:
            yield db

    with Session(registry_engine) as db:
        team_id = str(db.scalar(sa.select(Team.id)))
    app = create_app()
    app.dependency_overrides[get_db] = session
    headers = {
        "Authorization": "Bearer " + create_access_token({"sub": "pg2@example.test"})
    }
    data = {
        "slug": "pg-app",
        "name": "Postgres application",
        "owning_team_id": team_id,
        "owner_user_id": 2,
        "data_owner_user_id": 2,
        "repository_url": "https://github.com/example/postgres",
    }
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/applications", headers=headers, json=data)
        assert response.status_code == 201, response.text
        application_id = response.json()["id"]
        path = f"/api/v1/applications/{application_id}"
        assert (
            client.post("/api/v1/applications", headers=headers, json=data).status_code
            == 409
        )
        outsider = {
            "Authorization": "Bearer "
            + create_access_token({"sub": "pg3@example.test"})
        }
        assert client.get(path, headers=outsider).status_code == 404
        assert client.get("/api/v1/applications?limit=1", headers=outsider).json() == {
            "items": [],
            "next_cursor": None,
        }
        role = {"user_id": 3, "role": "viewer"}
        assert (
            client.post(path + "/roles", headers=headers, json=role).status_code == 201
        )
        assert (
            client.post(path + "/roles", headers=headers, json=role).status_code == 409
        )
        assert client.get(path, headers=outsider).status_code == 200
        assert (
            client.patch(
                path, headers=outsider, json={"expected_version": 1, "name": "No"}
            ).status_code
            == 403
        )
        with monkeypatch.context() as patch:

            def fail_audit(*args: object, **kwargs: object) -> None:
                raise RuntimeError("injected audit failure")

            patch.setattr(audit_service, "record_audit", fail_audit)
            assert (
                client.post(
                    "/api/v1/applications",
                    headers=headers,
                    json={**data, "slug": "rollback"},
                ).status_code
                == 500
            )
            assert (
                client.patch(
                    path,
                    headers=headers,
                    json={"expected_version": 1, "name": "Rollback"},
                ).status_code
                == 500
            )
            assert (
                client.post(
                    f"/api/v1/teams/{team_id}/members",
                    headers={
                        "Authorization": "Bearer "
                        + create_access_token({"sub": "pg1@example.test"})
                    },
                    json={"user_id": 3},
                ).status_code
                == 500
            )
        assert client.get(path, headers=headers).json()["version"] == 1
        assert (
            client.get(path, headers=headers).json()["name"] == "Postgres application"
        )
    with Session(registry_engine) as db:
        from models.platform import TeamMembership

        assert db.scalar(sa.select(sa.func.count()).select_from(Application)) == 1
        assert db.scalar(sa.select(sa.func.count()).select_from(ApplicationRole)) == 3
        assert db.scalar(sa.select(sa.func.count()).select_from(AuditEvent)) == 2
        assert db.scalar(sa.select(sa.func.count()).select_from(TeamMembership)) == 1
        # Database constraints hold even when bypassing request validation.
        for kwargs in (
            {"user_id": 2, "team_id": uuid.UUID(team_id), "role": "viewer"},
            {"role": "viewer"},
            {"user_id": 3, "role": "platform_admin"},
        ):
            with pytest.raises(sa.exc.IntegrityError):
                db.add(
                    ApplicationRole(application_id=uuid.UUID(application_id), **kwargs)
                )
                db.flush()
            db.rollback()


def test_concurrent_metadata_updates_have_one_winner(
    registry_engine: sa.Engine,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from models.database import User
    from models.platform import Application, AuditEvent, Team
    from models.platform_schemas import ApplicationCreate, ApplicationUpdate
    from services.application_service import create_application, update_application
    from services.policy_service import PolicyError
    from sqlalchemy.orm import Session

    with Session(registry_engine) as db:
        actor = db.get(User, 2)
        application = create_application(
            db,
            actor,
            ApplicationCreate(
                slug="race",
                name="Before",
                owning_team_id=db.scalar(sa.select(Team.id)),
                owner_user_id=2,
                data_owner_user_id=2,
                repository_url="https://github.com/example/race",
            ),
            str(uuid.uuid4()),
        )
        application_id = application.id
    barrier = Barrier(2)

    def change(name: str) -> str:
        with Session(registry_engine) as db:
            actor = db.get(User, 2)
            # Both requests have observed version 1 before attempting an update.
            assert db.get(Application, application_id).version == 1
            barrier.wait(timeout=10)
            try:
                update_application(
                    db,
                    actor,
                    application_id,
                    ApplicationUpdate(expected_version=1, name=name),
                    str(uuid.uuid4()),
                )
                return "updated"
            except PolicyError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, ["First", "Second"]))
    assert sorted(results) == ["stale_version", "updated"]
    with Session(registry_engine) as db:
        assert db.get(Application, application_id).version == 2
        assert (
            db.scalar(
                sa.select(sa.func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "application.updated")
            )
            == 1
        )
