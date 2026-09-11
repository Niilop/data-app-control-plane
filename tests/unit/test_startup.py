"""Fresh-process tests catch import-time configuration/provider coupling."""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
NETWORK_GUARD = """
import sys

def forbid_network(event, args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise AssertionError("Startup must not access the network")

sys.addaudithook(forbid_network)
"""


def run_isolated(script: str, tmp_path: Path) -> str:
    """Run without the user's environment, dotenv file, DB, or provider access."""
    result = subprocess.run(
        [sys.executable, "-c", NETWORK_GUARD + script],
        cwd=tmp_path,
        env={
            "PATH": os.environ["PATH"],
            "PYTHONPATH": str(BACKEND),
            "DATABASE_URL": "postgresql://test:test@127.0.0.1:1/unused",
            "SECRET_KEY": "unit-test-key-only",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_application_assembly_without_ai_or_network(tmp_path: Path) -> None:
    run_isolated(
        """
from fastapi.testclient import TestClient
from sqlalchemy.orm import configure_mappers
from main import app
from core.database import Base, engine

configure_mappers()
assert engine.echo is False
paths = app.openapi()["paths"]
assert {"/auth/login", "/auth/me", "/auth/register"} <= paths.keys()
assert "/metrics" not in paths
assert not {"models", "conversations", "messages", "document_chunks", "background_jobs"} & Base.metadata.tables.keys()
with TestClient(app) as client:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/").json() == {"message": "Data Application Control Plane is running"}
    assert client.get("/auth/me").status_code == 401
    for path in ("/llm/summarize", "/rag/query", "/chat/conversations", "/jobs/test"):
        assert client.get(path).status_code == 404
assert not any(name.startswith(("langchain", "google.genai", "services.llm", "services.rag", "pgvector")) for name in sys.modules)
""",
        tmp_path,
    )


def test_historical_migration_metadata_preserves_ai_tables(tmp_path: Path) -> None:
    run_isolated(
        f"""
from importlib.util import module_from_spec, spec_from_file_location
from sqlalchemy.orm import configure_mappers
from models.database import Base

spec = spec_from_file_location("legacy_models", {str(BACKEND / "alembic/legacy_models.py")!r})
spec.loader.exec_module(module_from_spec(spec))
configure_mappers()
assert {{"users", "models", "conversations", "messages", "document_chunks", "background_jobs"}} <= Base.metadata.tables.keys()
""",
        tmp_path,
    )


def test_migrations_render_offline_without_ai_configuration(tmp_path: Path) -> None:
    output = run_isolated(
        f"""
from alembic.config import Config
from alembic import command

config = Config({str(BACKEND / "alembic.ini")!r})
config.set_main_option("script_location", {str(BACKEND / "alembic")!r})
command.upgrade(config, "head", sql=True)
""",
        tmp_path,
    )
    assert "CREATE TABLE users" in output
    assert "CREATE TABLE document_chunks" in output
    assert "004_add_background_jobs" in output
    assert "CREATE TABLE applications" in output
    assert "005_owned_applications" in output
    assert "DROP TABLE" not in output
