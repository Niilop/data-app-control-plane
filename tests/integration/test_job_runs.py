"""Real PostgreSQL command serialization, migration preservation and run fencing."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker
from test_deployments import approved
from test_migrations import isolated_schema as isolated_schema
from test_migrations import registry_engine as registry_engine

pytestmark = pytest.mark.integration


def deployed(engine: sa.Engine, tmp_path, monkeypatch: pytest.MonkeyPatch):
    from models.database import User
    from models.deployment import Deployment
    from services.deployment_service import submit
    from worker import run_one

    app, data = approved(engine, tmp_path, monkeypatch)
    with Session(engine) as db:
        operation = submit(db, db.get(User, 2), app, data, "deploy", str(uuid4()))
        identifier = operation.id
    assert run_one(sessionmaker(engine), "deploy-worker")
    with Session(engine) as db:
        row = db.scalar(
            sa.select(Deployment).where(Deployment.operation_id == identifier)
        )
        assert row.status == "succeeded"
        return row.id, row.binding_id


def test_concurrent_run_keys_conflicts_and_fencing(
    registry_engine, tmp_path, monkeypatch
) -> None:
    from integrations.simulated_run import execute
    from models.database import User
    from models.job_run import JobRun
    from models.job_run_schemas import RunInput
    from models.operations import Operation, OperationReservation
    from models.platform import utcnow
    from services.job_run_service import submit
    from services.policy_service import PolicyError
    from services.queue_service import LostLease, claim, finish
    from worker import run_one

    deployment_id, binding_id = deployed(registry_engine, tmp_path, monkeypatch)
    data = RunInput(resource_key="synthetic_job", execution_mode="simulated")
    barrier = Barrier(2)

    def send(key: str):
        with Session(registry_engine) as db:
            actor = db.get(User, 2)
            barrier.wait(timeout=10)
            try:
                return submit(db, actor, deployment_id, data, key, str(uuid4())).id
            except PolicyError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(send, ["same", "same"]))
    assert ids[0] == ids[1] and ids[0] != "operation_conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(send, ["other1", "other2"])) == [
            "operation_conflict",
            "operation_conflict",
        ]
    with Session(registry_engine) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(JobRun)) == 1
    with Session(registry_engine) as db:
        stale = claim(db, "stale")
    with registry_engine.begin() as conn:
        conn.execute(
            sa.update(Operation)
            .where(Operation.id == ids[0])
            .values(lease_expires_at=utcnow() - timedelta(seconds=1))
        )
    with Session(registry_engine) as db:
        fresh = claim(db, "fresh")
        with pytest.raises(LostLease):
            finish(db, stale, "succeeded", run_result=execute(data))
        finish(db, fresh, "safe_to_retry")
        assert db.get(OperationReservation, binding_id) is not None
        db.get(Operation, ids[0]).available_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert run_one(sessionmaker(registry_engine), "recovered")
    with Session(registry_engine) as db:
        row = db.scalar(sa.select(JobRun))
        assert row.status == "succeeded" and row.result["output"]["total"] == 4950
        assert db.get(OperationReservation, binding_id) is None


def test_upgrade_preserves_deployment_and_downgrade_retains_runs(
    registry_engine, tmp_path, monkeypatch
) -> None:
    from alembic import command
    from models.database import User
    from models.job_run_schemas import RunInput
    from services.job_run_service import submit
    from test_migrations import _alembic_config

    deployment_id, _ = deployed(registry_engine, tmp_path, monkeypatch)
    with registry_engine.connect() as conn:
        before = conn.execute(
            sa.text("SELECT id, status, resources FROM deployments")
        ).all()
    command.downgrade(_alembic_config(), "009_simulated_deployments")
    command.upgrade(_alembic_config(), "head")
    with registry_engine.connect() as conn:
        assert (
            conn.execute(sa.text("SELECT id, status, resources FROM deployments")).all()
            == before
        )
    with Session(registry_engine) as db:
        submit(
            db,
            db.get(User, 2),
            deployment_id,
            RunInput(resource_key="synthetic_job", execution_mode="simulated"),
            "run",
            str(uuid4()),
        )
    with pytest.raises(RuntimeError, match="job run history"):
        command.downgrade(_alembic_config(), "009_simulated_deployments")
    with registry_engine.connect() as conn:
        assert conn.scalar(sa.text("SELECT count(*) FROM job_runs")) == 1
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "010_simulated_job_runs"
        )


def test_role_revoked_during_policy_lock_wait(
    registry_engine, tmp_path, monkeypatch
) -> None:
    from threading import Event

    from models.database import User
    from models.job_run_schemas import RunInput
    from models.platform import ApplicationRole, Environment, EnvironmentBinding
    from services.job_run_service import submit
    from services.policy_service import PolicyError

    deployment_id, binding_id = deployed(registry_engine, tmp_path, monkeypatch)
    reached_lock = Event()

    def waiting(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement and "environments" in statement:
            reached_lock.set()

    def send():
        with Session(registry_engine) as db:
            try:
                submit(
                    db,
                    db.get(User, 2),
                    deployment_id,
                    RunInput(resource_key="synthetic_job", execution_mode="simulated"),
                    "revoked",
                    str(uuid4()),
                )
            except PolicyError as exc:
                return exc.code
            return "unexpected_success"

    with Session(registry_engine) as blocker:
        binding = blocker.get(EnvironmentBinding, binding_id)
        blocker.scalar(
            sa.select(Environment)
            .where(Environment.id == binding.environment_id)
            .with_for_update()
        )
        sa.event.listen(registry_engine, "before_cursor_execute", waiting)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(send)
                try:
                    assert reached_lock.wait(timeout=10)
                    blocker.execute(
                        sa.delete(ApplicationRole).where(
                            ApplicationRole.user_id == 2,
                            ApplicationRole.role == "operator",
                        )
                    )
                finally:
                    blocker.commit()
                assert future.result(timeout=10) == "forbidden"
        finally:
            sa.event.remove(registry_engine, "before_cursor_execute", waiting)
    with registry_engine.connect() as conn:
        assert conn.scalar(sa.text("SELECT count(*) FROM job_runs")) == 0
