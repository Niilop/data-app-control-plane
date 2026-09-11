"""Real PostgreSQL generation, artifact persistence, revisions and validation."""

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker
from test_environment_bindings import setup_binding
from test_migrations import BACKEND
from test_migrations import isolated_schema as isolated_schema
from test_migrations import registry_engine as registry_engine
from test_operations import process_env

pytestmark = pytest.mark.integration

TEMPLATE = ("python-batch", "1.0.0")


@pytest.fixture
def artifact_dir(tmp_path: Path) -> Path:
    """A disposable store standing in for the shared mount the services configure."""
    directory = tmp_path / "artifacts"
    previous = os.environ.get("ARTIFACT_DIR")
    os.environ["ARTIFACT_DIR"] = str(directory)
    from core.config import get_settings

    get_settings.cache_clear()
    yield directory
    if previous is None:
        os.environ.pop("ARTIFACT_DIR", None)
    else:
        os.environ["ARTIFACT_DIR"] = previous
    get_settings.cache_clear()


def prepare(engine: sa.Engine) -> tuple[UUID, UUID]:
    """User 2 registers the application and so already holds developer and viewer."""
    app_id, _, binding_id = setup_binding(engine)
    return app_id, binding_id


def submit(engine: sa.Engine, app_id: UUID, binding_id: UUID, key: str) -> UUID:
    from models.database import User
    from models.delivery_schemas import GenerationInput
    from services.delivery_service import create_generation

    with Session(engine) as db:
        return create_generation(
            db,
            db.get(User, 2),
            app_id,
            GenerationInput(
                template_name=TEMPLATE[0],
                template_version=TEMPLATE[1],
                binding_id=binding_id,
                package_name="environment_app",
            ),
            key,
            str(uuid4()),
        ).id


def drain(engine: sa.Engine) -> None:
    from worker import run_one

    sessions = sessionmaker(engine)
    for _ in range(10):
        if not run_one(sessions, str(uuid4())):
            return
    raise AssertionError("Queue did not drain")


def test_generation_persists_an_artifact_and_takes_no_reservation(
    registry_engine: sa.Engine, artifact_dir: Path
) -> None:
    from integrations import artifact_store
    from models.delivery import Artifact
    from models.operations import Operation, OperationReservation

    app_id, binding_id = prepare(registry_engine)
    operation_id = submit(registry_engine, app_id, binding_id, "generate-1")
    with Session(registry_engine) as db:
        assert db.get(OperationReservation, binding_id) is None
        operation = db.get(Operation, operation_id)
        assert operation.kind == "bundle_generation"
        assert operation.execution_mode == "local"
    drain(registry_engine)
    with Session(registry_engine) as db:
        operation = db.get(Operation, operation_id)
        assert operation.status == "succeeded", operation.diagnostic_code
        artifact = db.scalar(sa.select(Artifact))
        assert artifact is not None
        assert artifact.kind == "generated_bundle"
        assert artifact.size_bytes > 0
    # The content is in the configured directory, not in any process's memory.
    stored = artifact_dir / artifact_store.storage_key(artifact.digest)
    assert stored.is_file()
    assert artifact_store.get(artifact.digest) == stored.read_bytes()


def test_separate_process_generates_the_same_digest(
    registry_engine: sa.Engine, isolated_schema: str, artifact_dir: Path
) -> None:
    """Determinism must hold across processes, not only within one interpreter."""
    from services.template_service import build_archive, get_template

    values = {
        "application_slug": "environment-app",
        "package_name": "environment_app",
        "package_dist_name": "environment-app",
        "bundle_target": "sandbox",
        "synthetic_output_path": "output/synthetic.csv",
        "synthetic_row_count": "100",
        "max_runtime_seconds": "300",
        "template_name": TEMPLATE[0],
        "template_version": TEMPLATE[1],
    }
    import hashlib
    import subprocess

    local = hashlib.sha256(build_archive(get_template(*TEMPLATE), values)).hexdigest()
    script = (
        "import hashlib, json;"
        "from services.template_service import build_archive, get_template;"
        f"values={values!r};"
        "print(hashlib.sha256("
        "build_archive(get_template('python-batch', '1.0.0'), values)).hexdigest())"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**process_env(isolated_schema), "ARTIFACT_DIR": str(artifact_dir)},
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == local


def test_concurrent_generations_share_one_stored_artifact(
    registry_engine: sa.Engine, artifact_dir: Path
) -> None:
    """Identical content is deduplicated by the unique (application, digest) key."""
    from models.delivery import Artifact

    app_id, binding_id = prepare(registry_engine)
    for index in range(3):
        submit(registry_engine, app_id, binding_id, f"generate-{index}")
    barrier = Barrier(3)

    def run() -> None:
        from worker import run_one

        barrier.wait(timeout=30)
        sessions = sessionmaker(registry_engine)
        for _ in range(4):
            run_one(sessions, str(uuid4()))

    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in [pool.submit(run) for _ in range(3)]:
            future.result(timeout=120)
    with Session(registry_engine) as db:
        artifacts = list(db.scalars(sa.select(Artifact)))
        assert len(artifacts) == 1
        assert db.scalar(sa.select(sa.func.count()).select_from(Artifact)) == 1


def test_revision_and_offline_validation_round_trip(
    registry_engine: sa.Engine, artifact_dir: Path
) -> None:
    from models.database import User
    from models.delivery import Artifact, ValidationResult
    from models.delivery_schemas import RevisionCreate
    from models.operations import Operation
    from services.delivery_service import create_revision, create_validation

    app_id, binding_id = prepare(registry_engine)
    submit(registry_engine, app_id, binding_id, "generate-revision")
    drain(registry_engine)
    with Session(registry_engine) as db:
        digest = db.scalar(sa.select(Artifact.digest))
        revision = create_revision(
            db,
            db.get(User, 2),
            app_id,
            RevisionCreate(artifact_digest=digest, binding_id=binding_id),
            str(uuid4()),
        )
        revision_id, scope_digest = revision.id, revision.scope_digest
        create_validation(db, db.get(User, 2), revision_id, "validate-1", str(uuid4()))
    drain(registry_engine)
    with Session(registry_engine) as db:
        result = db.scalar(sa.select(ValidationResult))
        assert result is not None
        assert result.scope == "offline"
        assert result.result == "passed", result.check_summary
        assert result.report_artifact_id is not None
        operation = db.get(Operation, result.operation_id)
        assert operation.execution_mode == "local"
        report = db.get(Artifact, result.report_artifact_id)
        assert report.media_type == "application/json"
        # Capturing the same inputs again yields the same approval scope.
        again = create_revision(
            db,
            db.get(User, 2),
            app_id,
            RevisionCreate(artifact_digest=digest, binding_id=binding_id),
            str(uuid4()),
        )
        assert again.id != revision_id
        assert again.scope_digest == scope_digest


def test_revision_rows_reject_an_unknown_source_kind(
    registry_engine: sa.Engine, artifact_dir: Path
) -> None:
    """The database, not only the service, refuses an unsupported source kind."""
    from models.delivery import DeploymentRevision

    app_id, binding_id = prepare(registry_engine)
    with Session(registry_engine) as db:
        with pytest.raises(sa.exc.IntegrityError):
            db.execute(
                sa.insert(DeploymentRevision).values(
                    id=uuid4(),
                    application_id=app_id,
                    source_kind="repository_commit",
                    artifact_id=uuid4(),
                    artifact_digest="a" * 64,
                    template_version_id=uuid4(),
                    binding_id=binding_id,
                    binding_version=1,
                    bundle_target="sandbox",
                    binding_snapshot={},
                    config_snapshot={},
                    config_digest="b" * 64,
                    scope_digest="c" * 64,
                    execution_mode="simulated",
                    requested_by=2,
                    request_id=str(uuid4()),
                    created_at=sa.func.now(),
                )
            )
        db.rollback()


def test_validation_rows_reject_a_workspace_scope(
    registry_engine: sa.Engine, artifact_dir: Path
) -> None:
    from models.delivery import ValidationResult

    app_id, binding_id = prepare(registry_engine)
    with Session(registry_engine) as db:
        with pytest.raises(sa.exc.IntegrityError):
            db.execute(
                sa.insert(ValidationResult).values(
                    id=uuid4(),
                    revision_id=uuid4(),
                    application_id=app_id,
                    operation_id=uuid4(),
                    scope="workspace",
                    validator="control-plane-offline",
                    validator_version="1.0.0",
                    tool_versions={},
                    result="passed",
                    check_summary={},
                    requested_by=2,
                    created_at=sa.func.now(),
                )
            )
        db.rollback()


def test_operations_reject_a_mislabelled_execution_mode(
    registry_engine: sa.Engine, artifact_dir: Path
) -> None:
    """Local work cannot be recorded as simulated, or a probe as local."""
    from models.operations import Operation

    app_id, binding_id = prepare(registry_engine)
    for kind, mode in (("bundle_generation", "simulated"), ("queue_probe", "local")):
        with Session(registry_engine) as db:
            with pytest.raises(sa.exc.IntegrityError):
                db.execute(
                    sa.insert(Operation).values(
                        id=uuid4(),
                        application_id=app_id,
                        binding_id=binding_id,
                        binding_version=1,
                        requested_by=2,
                        request_id=str(uuid4()),
                        kind=kind,
                        execution_mode=mode,
                        payload={},
                        status="queued",
                        available_at=sa.func.now(),
                        updated_at=sa.func.now(),
                        fencing_token=0,
                        attempt_count=0,
                        max_attempts=3,
                        cancel_requested=False,
                        created_at=sa.func.now(),
                    )
                )
            db.rollback()


def test_generation_stops_when_the_developer_role_is_revoked(
    registry_engine: sa.Engine, artifact_dir: Path
) -> None:
    from models.delivery import Artifact
    from models.operations import Operation
    from models.platform import ApplicationRole

    app_id, binding_id = prepare(registry_engine)
    operation_id = submit(registry_engine, app_id, binding_id, "generate-revoked")
    with Session(registry_engine) as db:
        db.execute(
            sa.delete(ApplicationRole).where(
                ApplicationRole.application_id == app_id,
                ApplicationRole.role == "developer",
            )
        )
        db.commit()
    drain(registry_engine)
    with Session(registry_engine) as db:
        operation = db.get(Operation, operation_id)
        assert operation.status == "failed"
        assert operation.diagnostic_code == "authorization_changed"
        assert db.scalar(sa.select(Artifact)) is None
