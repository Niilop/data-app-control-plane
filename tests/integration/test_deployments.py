"""PostgreSQL deployment submission serialization, immutable evidence and fencing."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker
from test_environment_bindings import setup_binding
from test_migrations import isolated_schema as isolated_schema
from test_migrations import registry_engine as registry_engine

pytestmark = pytest.mark.integration


def approved(engine: sa.Engine, tmp_path, monkeypatch: pytest.MonkeyPatch) -> tuple:
    from core.config import get_settings
    from models.database import User
    from models.delivery import Generation, ValidationResult
    from models.delivery_schemas import GenerationInput, RevisionInput
    from models.deployment_schemas import ApprovalInput, DeploymentInput
    from models.platform import ApplicationRole
    from services import delivery_service as preparation
    from services import deployment_service as deployment
    from services.template_service import canonical, sha
    from worker import run_one

    monkeypatch.setattr(get_settings(), "artifact_dir", str(tmp_path))
    app, _, binding = setup_binding(engine)
    with Session(engine) as db:
        db.add_all(
            [
                ApplicationRole(application_id=app, user_id=2, role="operator"),
                ApplicationRole(application_id=app, user_id=1, role="approver"),
            ]
        )
        db.commit()
        preparation.generate(
            db,
            db.get(User, 2),
            app,
            GenerationInput(binding_id=binding, expected_binding_version=1),
            "gen",
            str(uuid4()),
        )
    assert run_one(sessionmaker(engine), "prepare")
    with Session(engine) as db:
        generation = db.scalar(sa.select(Generation))
        row = preparation.create_revision(
            db,
            db.get(User, 2),
            app,
            RevisionInput(
                generation_id=generation.id,
                binding_id=binding,
                expected_binding_version=1,
            ),
            str(uuid4()),
        )
        revision_id = row.id
        preparation.validate(db, db.get(User, 2), row.id, "validate", str(uuid4()))
    assert run_one(sessionmaker(engine), "validate")
    with Session(engine) as db:
        from models.delivery import DeploymentRevision

        row = db.get(DeploymentRevision, revision_id)
        report = db.scalar(sa.select(ValidationResult))
        scope = deployment.scope_for(db, row, report.id)
        approval = deployment.approve(
            db,
            db.get(User, 1),
            row.id,
            ApprovalInput(
                validation_id=report.id,
                scope_digest=sha(canonical(scope)),
                decision="approved",
                reason="Independent simulated review",
            ),
            str(uuid4()),
        )
        return app, DeploymentInput(
            revision_id=row.id,
            approval_id=approval.id,
            binding_id=binding,
            execution_mode="simulated",
        )


def test_concurrent_duplicate_and_conflicting_deployments(
    registry_engine: sa.Engine, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.database import User
    from models.deployment import Deployment
    from models.operations import Operation, OperationReservation
    from services.deployment_service import submit
    from services.policy_service import PolicyError

    app, data = approved(registry_engine, tmp_path, monkeypatch)
    barrier = Barrier(2)

    def send(key: str) -> object:
        with Session(registry_engine) as db:
            actor = db.get(User, 2)
            barrier.wait(timeout=10)
            try:
                return submit(db, actor, app, data, key, str(uuid4())).id
            except PolicyError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(send, ["same", "same"]))
    assert result[0] == result[1] and result[0] != "operation_conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(send, ["different1", "different2"])) == [
            "operation_conflict",
            "operation_conflict",
        ]
    with Session(registry_engine) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(Deployment)) == 1
        assert (
            db.scalar(
                sa.select(sa.func.count())
                .select_from(Operation)
                .where(Operation.kind == "deploy_simulated")
            )
            == 1
        )
        assert (
            db.scalar(sa.select(sa.func.count()).select_from(OperationReservation)) == 1
        )
    for sql in ("UPDATE approvals SET scope_digest = 'bad'", "DELETE FROM approvals"):
        with registry_engine.connect() as conn:
            with pytest.raises(sa.exc.DBAPIError, match="immutable"):
                conn.execute(sa.text(sql))
            conn.rollback()


def test_expired_deployment_fence_and_partial_failure(
    registry_engine: sa.Engine, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import timedelta

    from models.database import User
    from models.deployment import Deployment
    from models.operations import Operation, OperationReservation
    from models.platform import utcnow
    from services.deployment_service import submit
    from services.queue_service import LostLease, authorize, claim, finish
    from worker import run_one

    app, data = approved(registry_engine, tmp_path, monkeypatch)
    with Session(registry_engine) as db:
        op_id = submit(db, db.get(User, 2), app, data, "first", str(uuid4())).id
    with Session(registry_engine) as db:
        item = claim(db, "stale")
        authorize(db, item)
    with registry_engine.begin() as conn:
        conn.execute(
            sa.update(Operation)
            .where(Operation.id == op_id)
            .values(lease_expires_at=utcnow() - timedelta(seconds=1))
        )
    with Session(registry_engine) as db:
        replacement = claim(db, "replacement")
        assert replacement.phase == "reconcile"
        with pytest.raises(LostLease):
            finish(db, item, "succeeded", deployment_resources=[])
        assert db.get(OperationReservation, data.binding_id).operation_id == op_id
        db.rollback()
        finish(db, replacement, "safe_to_retry")
    with registry_engine.begin() as conn:
        conn.execute(
            sa.update(Operation)
            .where(Operation.id == op_id)
            .values(available_at=utcnow() - timedelta(seconds=1))
        )
    assert run_one(sessionmaker(registry_engine), "complete")
    with Session(registry_engine) as db:
        assert db.scalar(sa.select(Deployment)).status == "succeeded"
        submit(
            db,
            db.get(User, 2),
            app,
            data.model_copy(update={"scenario": "partial_failure"}),
            "partial",
            str(uuid4()),
        )
    assert run_one(sessionmaker(registry_engine), "partial")
    with Session(registry_engine) as db:
        rows = list(db.scalars(sa.select(Deployment)))
        assert {row.status for row in rows} == {"succeeded", "failed"}
        assert all(row.resources and row.last_observed_at for row in rows)
        assert db.get(OperationReservation, data.binding_id) is None


def test_permission_revoked_while_submission_waits_for_policy_lock(
    registry_engine: sa.Engine, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from threading import Event

    from models.database import User
    from models.deployment import Deployment
    from models.platform import ApplicationRole, EnvironmentBinding
    from services import deployment_service as service
    from services.environment_service import lock_environment
    from services.policy_service import PolicyError

    app, data = approved(registry_engine, tmp_path, monkeypatch)
    waiting = Event()
    original_lock = service.lock_environment

    def tracked_lock(db: Session, identifier):
        waiting.set()
        return original_lock(db, identifier)

    monkeypatch.setattr(service, "lock_environment", tracked_lock)

    def submit() -> str:
        with Session(registry_engine) as db:
            try:
                service.submit(db, db.get(User, 2), app, data, "blocked", str(uuid4()))
            except PolicyError as exc:
                return exc.code
            return "unexpected_success"

    with Session(registry_engine) as blocker:
        binding = blocker.get(EnvironmentBinding, data.binding_id)
        lock_environment(blocker, binding.environment_id)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(submit)
            assert waiting.wait(timeout=10)
            blocker.execute(
                sa.delete(ApplicationRole).where(ApplicationRole.role == "operator")
            )
            blocker.commit()
            assert future.result(timeout=10) == "forbidden"
    with Session(registry_engine) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(Deployment)) == 0
