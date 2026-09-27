"""Exact approval, current policy, simulation failure, and queue recovery."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_delivery import revision


def prepared(registry: tuple, *, self_allowed: bool = False) -> tuple[dict, dict]:
    # Fixture config is applied before immutable capture, never to existing revisions.
    if self_allowed:
        from unittest.mock import patch

        from test_environments import environment_payload

        with patch(
            "test_environments.environment_payload",
            side_effect=lambda **kw: environment_payload(
                allow_self_approval=True, **kw
            ),
        ):
            row = revision(registry)
    else:
        row = revision(registry)
    client, headers, engine, _ = registry
    for actor, role in ((2, "operator"), (3, "approver"), (2, "approver")):
        response = client.post(
            f"/api/v1/applications/{row['application_id']}/roles",
            headers=headers[1],
            json={"user_id": actor, "role": role},
        )
        assert response.status_code == 201, response.text
    path = f"/api/v1/revisions/{row['id']}/validations"
    assert (
        client.post(
            path,
            headers={**headers[2], "Idempotency-Key": "validate"},
            json={"scope": "offline"},
        ).status_code
        == 202
    )
    from worker import run_one

    assert run_one(sessionmaker(engine), str(uuid4()))
    report = client.get(path, headers=headers[2]).json()["items"][0]
    assert report["result"] == "passed"
    return row, report


def decision(
    registry: tuple, row: dict, report: dict, *, actor: int = 3, **changes: object
):
    client, headers, _, _ = registry
    scope = client.get(
        f"/api/v1/revisions/{row['id']}/approval-scope",
        params={"validation_id": report["id"]},
        headers=headers[actor],
    )
    assert scope.status_code == 200, scope.text
    return client.post(
        f"/api/v1/revisions/{row['id']}/approvals",
        headers=headers[actor],
        json={
            "validation_id": report["id"],
            "scope_digest": scope.json()["scope_digest"],
            "decision": "approved",
            "reason": "Reviewed exact local scope",
            **changes,
        },
    )


def approved(registry: tuple) -> tuple[dict, dict]:
    row, report = prepared(registry)
    response = decision(registry, row, report)
    assert response.status_code == 201, response.text
    return row, response.json()


def deploy(
    registry: tuple,
    row: dict,
    approval: dict,
    key: str = "deploy",
    actor: int = 2,
    **changes: object,
):
    client, headers, _, _ = registry
    return client.post(
        f"/api/v1/applications/{row['application_id']}/deployments",
        headers={**headers[actor], "Idempotency-Key": key},
        json={
            "revision_id": row["id"],
            "approval_id": approval["id"],
            "binding_id": row["binding_id"],
            "execution_mode": "simulated",
            **changes,
        },
    )


def test_success_partial_failure_replay_and_last_success(registry: tuple) -> None:
    from models.platform import Application
    from worker import run_one

    row, approval = approved(registry)
    first = deploy(registry, row, approval)
    assert first.status_code == 202, first.text
    assert first.json()["execution_mode"] == "simulated"
    assert deploy(registry, row, approval).json() == first.json()
    assert deploy(registry, row, approval, "conflict").status_code == 409
    assert (
        deploy(registry, row, approval, scenario="partial_failure").status_code == 409
    )
    client, headers, engine, _ = registry
    assert run_one(sessionmaker(engine), str(uuid4()))
    path = f"/api/v1/applications/{row['application_id']}"
    success = client.get(
        f"{path}/bindings/{row['binding_id']}/last-success", headers=headers[2]
    ).json()
    assert (
        success["status"] == "succeeded"
        and success["resources"][0]["status"] == "ready"
    )
    assert (
        deploy(
            registry, row, approval, "partial", scenario="partial_failure"
        ).status_code
        == 202
    )
    assert run_one(sessionmaker(engine), str(uuid4()))
    rows = client.get(path + "/deployments", headers=headers[2]).json()["items"]
    assert len(rows) == 2
    failed = next(d for d in rows if d["status"] == "failed")
    assert failed["resources"][0]["status"] == "created"
    assert all(d["execution_mode"] == "simulated" for d in rows)
    assert (
        client.get(
            f"{path}/bindings/{row['binding_id']}/last-success", headers=headers[2]
        ).json()
        == success
    )
    with Session(engine) as db:
        assert db.get(Application, UUID(row["application_id"])).lifecycle == "active"
    for endpoint in (
        path + "/deployments",
        f"/api/v1/deployments/{success['id']}",
        f"/api/v1/revisions/{row['id']}/approvals",
        f"{path}/bindings/{row['binding_id']}/last-success",
    ):
        assert client.get(endpoint, headers=headers[5]).status_code == 404
        assert client.get(endpoint).status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        "developer",
        "operator",
        "approver",
        "requester_inactive",
        "approver_inactive",
        "archived",
        "disabled",
        "target",
        "binding",
        "policy",
        "template",
    ],
)
def test_worker_rechecks_policy(registry: tuple, change: str) -> None:
    from models.database import User
    from models.delivery import TemplateVersion
    from models.deployment import Deployment
    from models.operations import Operation, OperationReservation
    from models.platform import (
        Application,
        ApplicationRole,
        Environment,
        EnvironmentBinding,
    )
    from worker import run_one

    row, approval = approved(registry)
    response = deploy(registry, row, approval)
    assert response.status_code == 202
    with Session(registry[2]) as db:
        binding = db.get(EnvironmentBinding, UUID(row["binding_id"]))
        environment = db.get(Environment, binding.environment_id)
        if change in {"developer", "operator", "approver"}:
            db.execute(delete(ApplicationRole).where(ApplicationRole.role == change))
        elif change.endswith("inactive"):
            db.get(User, 2 if change == "requester_inactive" else 3).is_active = False
        elif change == "archived":
            db.get(Application, UUID(row["application_id"])).lifecycle = "archived"
        elif change == "disabled":
            environment.enabled = False
        elif change == "target":
            environment.allowed_bundle_targets = ["other"]
        elif change == "policy":
            environment.allow_self_approval = True
        elif change == "binding":
            binding.config = {**binding.config, "synthetic_row_count": 200}
        else:
            db.get(TemplateVersion, row["template_id"]).active = False
        db.commit()
    assert run_one(sessionmaker(registry[2]), str(uuid4()))
    with Session(registry[2]) as db:
        operation = db.get(Operation, UUID(response.json()["operation_id"]))
        assert (
            operation.status == "failed"
            and operation.diagnostic_code == "authorization_changed"
        )
        deployment = db.scalar(select(Deployment))
        assert deployment.status == "failed" and deployment.resources == []
        assert db.scalar(select(func.count()).select_from(OperationReservation)) == 0


def test_scope_permissions_and_failed_validation(registry: tuple) -> None:
    row, report = prepared(registry)
    assert decision(registry, row, report, scope_digest="0" * 64).status_code == 409
    assert (
        decision(registry, row, report, validation_id=str(uuid4())).status_code == 409
    )
    assert decision(registry, row, report, actor=1).status_code == 403
    reject = decision(registry, row, report, decision="rejected")
    assert reject.status_code == 201
    assert deploy(registry, row, reject.json()).status_code == 409
    approval = decision(registry, row, report).json()
    assert deploy(registry, row, approval, revision_id=str(uuid4())).status_code == 404
    assert deploy(registry, row, approval, binding_id=str(uuid4())).status_code == 422
    assert deploy(registry, row, approval, execution_mode="real").status_code == 422
    for actor in (1, 3, 4):
        assert deploy(registry, row, approval, actor=actor).status_code == 403
    from models.platform import ApplicationRole

    with Session(registry[2]) as db:
        db.execute(delete(ApplicationRole).where(ApplicationRole.role == "developer"))
        db.commit()
    assert deploy(registry, row, approval).status_code == 403


@pytest.mark.parametrize("allowed", [False, True])
def test_explicit_audited_self_approval(registry: tuple, allowed: bool) -> None:
    from models.platform import AuditEvent

    row, report = prepared(registry, self_allowed=allowed)
    assert decision(registry, row, report, actor=2).status_code == 403
    response = decision(
        registry, row, report, actor=2, acknowledge_local_self_approval=True
    )
    assert response.status_code == (201 if allowed else 403), response.text
    if allowed:
        assert deploy(registry, row, response.json()).status_code == 202
        with Session(registry[2]) as db:
            event = db.scalar(
                select(AuditEvent).where(AuditEvent.action == "approval.recorded")
            )
            assert event.details["local_self_approval"] is True
            assert event.details["self_approval_acknowledged"] is True


def test_fencing_recovery_cancel_retry_and_completion_recheck(registry: tuple) -> None:
    from models.deployment import Deployment
    from models.operations import Operation, OperationReservation
    from models.platform import ApplicationRole
    from services.queue_service import LostLease, authorize, claim, finish
    from test_operations import due
    from worker import run_one

    row, approval = approved(registry)
    response = deploy(registry, row, approval)
    op_id = UUID(response.json()["operation_id"])
    engine = registry[2]
    with Session(engine) as db:
        item = claim(db, "old")
        authorize(db, item)
    due(engine, op_id, expire=True)
    with Session(engine) as db:
        with pytest.raises(LostLease):
            finish(db, item, "succeeded", deployment_resources=[])
        assert db.scalar(select(Deployment)).status == "deploying"
        assert db.get(OperationReservation, UUID(row["binding_id"])) is not None
    assert run_one(sessionmaker(engine), "recover")
    due(engine, op_id)
    with Session(engine) as db:
        item = claim(db, "new")
        authorize(db, item)
    with Session(engine) as db:
        db.execute(delete(ApplicationRole).where(ApplicationRole.role == "approver"))
        db.commit()
    with Session(engine) as db:
        finish(
            db,
            item,
            "succeeded",
            deployment_resources=[{"execution_mode": "simulated", "status": "ready"}],
        )
        assert db.get(Operation, op_id).status == "failed"
        assert db.scalar(select(Deployment)).resources
    client, headers, _, _ = registry
    retry = client.post(
        f"/api/v1/operations/{op_id}/retry",
        headers={**headers[2], "Idempotency-Key": "retry"},
        json={},
    )
    assert retry.status_code == 403
    assert (
        client.post(
            f"/api/v1/applications/{row['application_id']}/roles",
            headers=headers[1],
            json={"user_id": 3, "role": "approver"},
        ).status_code
        == 201
    )
    retry = client.post(
        f"/api/v1/operations/{op_id}/retry",
        headers={**headers[2], "Idempotency-Key": "retry"},
        json={},
    )
    assert retry.status_code == 202, retry.text
    new_id = retry.json()["operation_id"]
    assert new_id != str(op_id)
    assert (
        client.post(
            f"/api/v1/operations/{new_id}/cancel",
            headers={**headers[2], "Idempotency-Key": "cancel"},
            json={},
        ).status_code
        == 202
    )
    with Session(engine) as db:
        assert (
            db.scalar(
                select(Deployment).where(Deployment.operation_id == UUID(new_id))
            ).status
            == "cancelled"
        )
        assert db.get(OperationReservation, UUID(row["binding_id"])) is None


def test_audit_failure_rolls_back_whole_submission(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.deployment import Deployment
    from models.operations import Operation, OperationCommand, OperationReservation
    from services import audit_service

    row, approval = approved(registry)
    with Session(registry[2]) as db:
        counts = [
            db.scalar(select(func.count()).select_from(model))
            for model in (Operation, OperationCommand)
        ]

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("private failure")

    monkeypatch.setattr(audit_service, "record_audit", fail)
    assert deploy(registry, row, approval).status_code == 500
    with Session(registry[2]) as db:
        assert [
            db.scalar(select(func.count()).select_from(model))
            for model in (Operation, OperationCommand)
        ] == counts
        assert db.scalar(select(func.count()).select_from(Deployment)) == 0
        assert db.scalar(select(func.count()).select_from(OperationReservation)) == 0


def test_report_and_revision_substitution_and_old_report_preserved(
    registry: tuple,
) -> None:
    from worker import run_one

    row, report = prepared(registry)
    approval = decision(registry, row, report).json()
    client, headers, engine, _ = registry
    second = client.post(
        f"/api/v1/applications/{row['application_id']}/revisions",
        headers=headers[2],
        json={
            "generation_id": row["generation_id"],
            "binding_id": row["binding_id"],
            "expected_binding_version": 1,
        },
    ).json()
    assert (
        client.get(
            f"/api/v1/revisions/{second['id']}/approval-scope",
            params={"validation_id": report["id"]},
            headers=headers[3],
        ).status_code
        == 409
    )
    assert deploy(registry, second, approval).status_code == 409
    # A later report never rewrites existing approval evidence.
    path = f"/api/v1/revisions/{row['id']}/validations"
    assert (
        client.post(
            path,
            headers={**headers[2], "Idempotency-Key": "later-report"},
            json={"scope": "offline"},
        ).status_code
        == 202
    )
    assert run_one(sessionmaker(engine), "later-report")
    reports = client.get(path, headers=headers[2]).json()["items"]
    newer = next(r for r in reports if r["id"] != report["id"])
    assert (
        decision(
            registry, row, newer, scope_digest=approval["scope_digest"]
        ).status_code
        == 409
    )
    assert (
        client.get(
            f"/api/v1/revisions/{row['id']}/approvals", headers=headers[2]
        ).json()["items"][0]
        == approval
    )
    assert deploy(registry, row, approval).status_code == 202


def test_failed_report_cannot_be_approved(registry: tuple) -> None:
    from services.delivery_service import store
    from worker import run_one

    row, _ = prepared(registry)
    (store().root / row["artifact_digest"]).write_bytes(b"corrupted")
    client, headers, engine, _ = registry
    path = f"/api/v1/revisions/{row['id']}/validations"
    assert (
        client.post(
            path,
            headers={**headers[2], "Idempotency-Key": "failed-report"},
            json={"scope": "offline"},
        ).status_code
        == 202
    )
    assert run_one(sessionmaker(engine), "failed-report")
    failed = next(
        r
        for r in client.get(path, headers=headers[2]).json()["items"]
        if r["result"] == "failed"
    )
    assert (
        client.post(
            f"/api/v1/revisions/{row['id']}/approvals",
            headers=headers[3],
            json={
                "validation_id": failed["id"],
                "scope_digest": "0" * 64,
                "decision": "approved",
                "reason": "Cannot approve failure",
            },
        ).status_code
        == 409
    )


def test_binding_edit_invalidates_approval_and_submission(registry: tuple) -> None:
    row, report = prepared(registry)
    approval = decision(registry, row, report).json()
    client, headers, _, _ = registry
    path = f"/api/v1/applications/{row['application_id']}/bindings/{row['binding_id']}"
    assert (
        client.patch(
            path,
            headers=headers[1],
            json={
                "expected_version": 1,
                "config": {
                    "schema_version": 1,
                    "synthetic_row_count": 200,
                    "max_runtime_seconds": 300,
                },
            },
        ).status_code
        == 200
    )
    assert decision(registry, row, report).status_code == 409
    assert deploy(registry, row, approval).status_code == 409


def test_result_audit_failure_preserves_reservation_and_state(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.deployment import Deployment
    from models.operations import Operation, OperationReservation
    from models.platform import Application
    from services import audit_service
    from services.queue_service import claim, finish

    row, approval = approved(registry)
    accepted = deploy(registry, row, approval).json()
    with Session(registry[2]) as db:
        item = claim(db, "audit-failure")

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Audit unavailable")

    monkeypatch.setattr(audit_service, "record_audit", fail)
    with Session(registry[2]) as db:
        with pytest.raises(RuntimeError, match="Audit unavailable"):
            finish(
                db,
                item,
                "succeeded",
                deployment_resources=[
                    {"execution_mode": "simulated", "status": "ready"}
                ],
            )
        assert db.get(Operation, UUID(accepted["operation_id"])).status == "running"
        assert db.scalar(select(Deployment)).resources == []
        assert db.get(OperationReservation, UUID(row["binding_id"])) is not None
        assert (
            db.get(Application, UUID(row["application_id"])).lifecycle == "registered"
        )


def test_new_decision_supersedes_old_approval_before_worker_execution(
    registry: tuple,
) -> None:
    from models.deployment import Deployment
    from worker import run_one

    row, report = prepared(registry)
    approval = decision(registry, row, report).json()
    assert deploy(registry, row, approval).status_code == 202
    assert decision(registry, row, report, decision="rejected").status_code == 201
    assert run_one(sessionmaker(registry[2]), "superseded")
    with Session(registry[2]) as db:
        assert db.scalar(select(Deployment)).status == "failed"
    assert deploy(registry, row, approval, "new-request").status_code == 409
