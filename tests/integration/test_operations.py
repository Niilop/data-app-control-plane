"""Real PostgreSQL queue contention, process loss, recovery and transaction tests."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from test_environment_bindings import setup_binding
from test_migrations import BACKEND, _scoped_database_url
from test_migrations import isolated_schema as isolated_schema
from test_migrations import registry_engine as registry_engine

pytestmark = pytest.mark.integration


def prepare(engine: sa.Engine) -> tuple[UUID, UUID]:
    from models.platform import ApplicationRole

    app_id, _, binding_id = setup_binding(engine)
    with Session(engine) as db:
        db.add(ApplicationRole(application_id=app_id, user_id=2, role="operator"))
        db.commit()
    return app_id, binding_id


def submit(
    engine: sa.Engine, app_id: UUID, binding_id: UUID, key: str = "probe"
) -> UUID:
    from models.database import User
    from models.operation_schemas import ProbeInput
    from services.operation_service import create_probe

    with Session(engine) as db:
        return create_probe(
            db, db.get(User, 2), app_id, binding_id, ProbeInput(), key, str(uuid4())
        ).id


def process_env(schema: str) -> dict[str, str]:
    return {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": str(BACKEND),
        "DATABASE_URL": _scoped_database_url(schema),
        "SECRET_KEY": "queue-integration-only",
        "DEBUG": "false",
        "RUNTIME_PROFILE": "local",
        "DEPLOYMENT_EXECUTOR": "simulated",
    }


def process(script: str, schema: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=process_env(schema),
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_two_process_claims_restart_reconciliation_and_fencing(
    registry_engine: sa.Engine, isolated_schema: str
) -> None:
    from models.operations import (
        Operation,
        OperationAttempt,
        OperationReservation,
        QueueProbe,
    )
    from models.platform import utcnow
    from services.queue_service import Claim, LostLease, finish, heartbeat

    app_id, binding_id = prepare(registry_engine)
    identifier = submit(registry_engine, app_id, binding_id)
    code = """
import json, sys
from uuid import uuid4
from core.database import SessionLocal
from services.queue_service import claim
print("ready", flush=True)
sys.stdin.readline()
with SessionLocal() as db:
    item = claim(db, str(uuid4()))
    print(json.dumps(None if item is None else {"worker_id":item.worker_id,"token":item.token}), flush=True)
"""
    children = [
        subprocess.Popen(
            [sys.executable, "-c", code],
            env=process_env(isolated_schema),
            cwd=BACKEND,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    try:
        for child in children:
            assert child.stdout.readline().strip() == "ready"
        for child in children:
            child.stdin.write("claim\n")
            child.stdin.flush()
        results = []
        for child in children:
            stdout, stderr = child.communicate(timeout=30)
            assert child.returncode == 0, stderr
            results.append(json.loads(stdout))
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
    winners = [result for result in results if result]
    assert len(winners) == 1
    old = Claim(
        identifier,
        winners[0]["worker_id"],
        winners[0]["token"],
        "execute",
        "queue_probe",
        {},
        1,
    )
    # Fresh API processes retain the same operation, including after a worker exits.
    api_read = f"""
from fastapi.testclient import TestClient
from main import create_app
from services.auth_service import create_access_token
with TestClient(create_app()) as client:
    response = client.get("/api/v1/operations/{identifier}", headers={{"Authorization":"Bearer " + create_access_token({{"sub":"pg2@example.test"}})}})
    assert response.status_code == 200, response.text
    print(response.json()["status"])
"""
    assert process(api_read, isolated_schema).strip() == "running"
    assert process(api_read, isolated_schema).strip() == "running"
    with Session(registry_engine) as db:
        db.get(Operation, identifier).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        with pytest.raises(LostLease):
            finish(db, old, "succeeded")
    # Independently restarted worker reconciles, schedules a safe retry, then finishes.
    process(
        "from worker import main; import sys; sys.argv=['worker','--once']; main()",
        isolated_schema,
    )
    with Session(registry_engine) as db:
        operation = db.get(Operation, identifier)
        assert operation.status == "retry_wait"
        assert operation.fencing_token > old.token
        assert db.get(OperationReservation, binding_id) is not None
        assert db.scalar(sa.select(QueueProbe.result)) is None
        operation.available_at = utcnow() - timedelta(seconds=1)
        db.commit()
        with pytest.raises(LostLease):
            heartbeat(db, old)
        with pytest.raises(LostLease):
            finish(db, old, "succeeded")
    process(
        "from worker import main; import sys; sys.argv=['worker','--once']; main()",
        isolated_schema,
    )
    assert process(api_read, isolated_schema).strip() == "succeeded"
    with Session(registry_engine) as db:
        assert db.scalar(sa.select(QueueProbe.result)) == "succeeded"
        assert db.get(OperationReservation, binding_id) is None
        assert db.scalar(sa.select(sa.func.count()).select_from(OperationAttempt)) == 3


def test_concurrent_idempotency_and_conflict_reservation(
    registry_engine: sa.Engine,
) -> None:
    from models.operations import Operation, OperationCommand, QueueProbe
    from services.policy_service import PolicyError

    app_id, binding_id = prepare(registry_engine)
    barrier = Barrier(2)

    def same(_: int) -> UUID:
        barrier.wait(timeout=10)
        return submit(registry_engine, app_id, binding_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        identifiers = list(pool.map(same, range(2)))
    assert len(set(identifiers)) == 1
    with pytest.raises(PolicyError) as conflict:
        submit(registry_engine, app_id, binding_id, "different")
    assert conflict.value.code == "operation_conflict"
    with Session(registry_engine) as db:
        for model in (Operation, OperationCommand, QueueProbe):
            assert db.scalar(sa.select(sa.func.count()).select_from(model)) == 1


def test_queue_and_completion_audit_failures_rollback_all_state(
    registry_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.operations import (
        Operation,
        OperationAttempt,
        OperationCommand,
        OperationReservation,
        QueueProbe,
    )
    from models.platform import AuditEvent
    from services import audit_service
    from services.queue_service import claim, finish

    app_id, binding_id = prepare(registry_engine)

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected transaction failure")

    with monkeypatch.context() as patch:
        patch.setattr(audit_service, "record_audit", fail)
        with pytest.raises(RuntimeError):
            submit(registry_engine, app_id, binding_id)
    with Session(registry_engine) as db:
        for model in (Operation, OperationCommand, OperationReservation, QueueProbe):
            assert db.scalar(sa.select(sa.func.count()).select_from(model)) == 0
    identifier = submit(registry_engine, app_id, binding_id)
    with Session(registry_engine) as db:
        item = claim(db, str(uuid4()))
    with Session(registry_engine) as db:
        before = db.scalar(sa.select(sa.func.count()).select_from(AuditEvent))
        db.rollback()
        with monkeypatch.context() as patch:
            patch.setattr(audit_service, "record_audit", fail)
            with pytest.raises(RuntimeError):
                finish(db, item, "succeeded")
        assert db.get(Operation, identifier).status == "running"
        assert db.scalar(sa.select(QueueProbe.result)) is None
        assert db.scalar(sa.select(OperationAttempt.outcome)) == "running"
        assert db.get(OperationReservation, binding_id) is not None
        assert db.scalar(sa.select(sa.func.count()).select_from(AuditEvent)) == before


def test_t03_binding_survives_queue_migration_round_trip(
    registry_engine: sa.Engine,
) -> None:
    from alembic import command
    from models.platform import EnvironmentBinding
    from test_migrations import _alembic_config

    app_id, binding_id = prepare(registry_engine)
    with Session(registry_engine) as db:
        binding = db.get(EnvironmentBinding, binding_id)
        before = (binding.version, binding.config, binding.bundle_target)
    command.downgrade(_alembic_config(), "006_environment_bindings")
    with Session(registry_engine) as db:
        binding = db.get(EnvironmentBinding, binding_id)
        assert (binding.version, binding.config, binding.bundle_target) == before
    command.upgrade(_alembic_config(), "head")
    with Session(registry_engine) as db:
        binding = db.get(EnvironmentBinding, binding_id)
        assert (binding.version, binding.config, binding.bundle_target) == before
    assert submit(registry_engine, app_id, binding_id)


def test_worker_process_heartbeat_and_running_cancellation(
    registry_engine: sa.Engine, isolated_schema: str
) -> None:
    import time

    from models.database import User
    from models.operation_schemas import ProbeInput
    from models.operations import Operation, OperationReservation, QueueProbe
    from services.operation_service import command, create_probe
    from services.queue_service import aware

    app_id, binding_id = prepare(registry_engine)
    with Session(registry_engine) as db:
        identifier = create_probe(
            db,
            db.get(User, 2),
            app_id,
            binding_id,
            ProbeInput(delay_seconds=10),
            "heartbeat",
            str(uuid4()),
        ).id
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from core.database import SessionLocal; from worker import run_one; from uuid import uuid4; assert run_one(SessionLocal, str(uuid4()), lease_seconds=2)",
        ],
        env=process_env(isolated_schema),
        cwd=BACKEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        started = time.monotonic()
        initial_heartbeat = None
        observed_heartbeat = False
        while time.monotonic() - started < 10:
            with Session(registry_engine) as db:
                operation = db.get(Operation, identifier)
                if operation.heartbeat_at:
                    if initial_heartbeat is None:
                        initial_heartbeat = operation.heartbeat_at
                    elif aware(operation.heartbeat_at) > aware(initial_heartbeat):
                        observed_heartbeat = True
                        result = command(
                            db,
                            db.get(User, 2),
                            identifier,
                            "cancel",
                            "cancel-running",
                            str(uuid4()),
                            {},
                        )
                        assert result.status == "running" and result.cancel_requested
                        break
            time.sleep(0.05)
        assert observed_heartbeat, "Worker did not renew its active lease"
        stdout, stderr = child.communicate(timeout=15)
        assert child.returncode == 0, stdout + stderr
        with Session(registry_engine) as db:
            assert db.get(Operation, identifier).status == "cancelled"
            assert db.scalar(sa.select(QueueProbe.result)) == "cancelled"
            assert db.get(OperationReservation, binding_id) is None
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
