"""Isolated PostgreSQL integration tests for the Alembic migration chain.

Require a real, pgvector-capable PostgreSQL reachable via TEST_DATABASE_URL.
Never run against a developer's primary or shared database: each test runs
inside a uniquely named, disposable schema that is dropped afterward. Skipped
with a visible reason when TEST_DATABASE_URL is unset.
"""

import os
import uuid
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
}
HEAD_REVISION = "004_add_background_jobs"


def _scoped_url(schema: str) -> str:
    """Same database as TEST_DATABASE_URL, scoped to an isolated schema."""
    assert TEST_DATABASE_URL is not None
    url = make_url(TEST_DATABASE_URL)
    query = {**url.query, "options": f"-c search_path={schema},public"}
    return url.set(query=query).render_as_string(hide_password=False)


def _alembic_config(scoped_url: str) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", scoped_url)
    return config


@pytest.fixture
def isolated_schema() -> str:
    """A uniquely named, disposable schema; dropped after the test regardless."""
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
        yield schema
    finally:
        with engine.begin() as conn:
            conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_pgvector_extension_is_available(isolated_schema: str) -> None:
    engine = sa.create_engine(_scoped_url(isolated_schema))
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
    scoped_url = _scoped_url(isolated_schema)
    command.upgrade(_alembic_config(scoped_url), "head")

    engine = sa.create_engine(scoped_url)
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
    scoped_url = _scoped_url(isolated_schema)
    config = _alembic_config(scoped_url)
    command.upgrade(config, "001_initial")

    engine = sa.create_engine(scoped_url)
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
