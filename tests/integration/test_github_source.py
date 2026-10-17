"""PostgreSQL source pins, fencing, migration guards and history preservation."""

import io
import zipfile
from datetime import timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.orm import Session, sessionmaker
from test_environment_bindings import setup_binding
from test_migrations import HEAD_REVISION, _alembic_config
from test_migrations import isolated_schema as isolated_schema
from test_migrations import registry_engine as registry_engine

pytestmark = pytest.mark.integration


def test_source_pins_fences_and_history_guard(
    registry_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from core.config import get_settings
    from integrations.github import GitHub
    from models.database import User
    from models.delivery_schemas import TemplateParameters
    from models.operations import Operation
    from models.platform import EnvironmentBinding, utcnow
    from models.source import SourceCapture
    from models.source_schemas import SourceInput
    from services.queue_service import LostLease, claim, finish
    from services.source_service import capture, execute
    from services.template_service import render, unpack

    settings = get_settings()
    monkeypatch.setattr(settings, "github_reads_enabled", True)
    monkeypatch.setattr(
        settings, "github_allowed_repositories", ["example/environments"]
    )
    monkeypatch.setattr(settings, "artifact_dir", str(tmp_path))
    app, _, binding_id = setup_binding(registry_engine)
    sessions = sessionmaker(registry_engine)
    with sessions() as db:
        binding = db.get(EnvironmentBinding, binding_id)
        files = unpack(
            render("environment-app", "sandbox", binding.config, TemplateParameters())
        )
        operation_id = capture(
            db,
            db.get(User, 2),
            app,
            SourceInput(binding_id=binding_id, expected_binding_version=1, ref="main"),
            "capture",
            str(uuid4()),
        ).id
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr("github-root/" + name, data)
    monkeypatch.setattr(GitHub, "resolve", lambda *_: (42, "a" * 40))
    monkeypatch.setattr(GitHub, "verify_repository", lambda *_: None)
    monkeypatch.setattr(GitHub, "archive", lambda *_: buffer.getvalue())
    with sessions() as db:
        item = claim(db, "old-worker", 30)
    result = execute(sessions, item)
    with registry_engine.connect() as connection:
        row = connection.execute(
            sa.text("SELECT commit_sha, artifact_digest FROM source_captures")
        ).one()
        assert row == ("a" * 40, None)  # Resolution committed before completion.
    with pytest.raises(sa.exc.DBAPIError, match="immutable"):
        with registry_engine.begin() as connection:
            connection.execute(
                sa.text("UPDATE source_captures SET commit_sha = :sha"),
                {"sha": "b" * 40},
            )
    with sessions() as db:
        db.get(Operation, operation_id).lease_expires_at = utcnow() - timedelta(
            seconds=1
        )
        db.commit()
    with sessions() as db, pytest.raises(LostLease):
        finish(db, item, "succeeded", source_result=result)
    with sessions() as db:
        assert db.scalar(sa.select(SourceCapture)).artifact_digest is None
        db.rollback()  # End the assertion's read transaction before the queue command.
        newer = claim(db, "new-worker", 30)
        assert newer.phase == "reconcile"
        finish(db, newer, "safe_to_retry")
    with sessions() as db:
        db.get(Operation, operation_id).available_at = utcnow()
        db.commit()
    monkeypatch.setattr(
        GitHub,
        "resolve",
        lambda *_: pytest.fail("Recovery must keep the pinned commit"),
    )
    from worker import run_one

    assert run_one(sessions, "new-worker")
    with sessions() as db:
        assert db.get(Operation, operation_id).status == "succeeded"
        assert db.scalar(sa.select(SourceCapture)).artifact_digest == result["digest"]
    with pytest.raises(RuntimeError, match="GitHub source history"):
        command.downgrade(_alembic_config(), "011_platform_access")
    with registry_engine.connect() as connection:
        assert (
            connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == HEAD_REVISION
        )


def test_ci_rows_are_append_only_in_postgres(
    registry_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.config import get_settings
    from models.database import User
    from models.platform import utcnow
    from models.source import CIRun, SourceCapture
    from models.source_schemas import SourceInput
    from services.source_service import capture

    app, _, binding = setup_binding(registry_engine)
    monkeypatch.setattr(get_settings(), "github_reads_enabled", True)
    monkeypatch.setattr(
        get_settings(), "github_allowed_repositories", ["example/environments"]
    )
    with Session(registry_engine) as db:
        operation = capture(
            db,
            db.get(User, 2),
            app,
            SourceInput(binding_id=binding, expected_binding_version=1, ref="main"),
            "capture",
            str(uuid4()),
        )
        source = db.scalar(sa.select(SourceCapture))
        source.commit_sha, source.repository_id = "a" * 40, 42
        db.add(
            CIRun(
                application_id=app,
                source_capture_id=source.id,
                operation_id=operation.id,
                commit_sha=source.commit_sha,
                run_id=1,
                run_attempt=1,
                workflow_id=2,
                status="completed",
                conclusion="success",
                event="push",
                url="https://github.com/example/environments/actions/runs/1",
                observed_at=utcnow(),
            )
        )
        db.commit()
    for statement in (
        "UPDATE ci_runs SET conclusion = 'failure'",
        "DELETE FROM ci_runs",
        "DELETE FROM source_captures",
    ):
        with pytest.raises(sa.exc.DBAPIError, match="immutable"):
            with registry_engine.begin() as connection:
                connection.execute(sa.text(statement))
