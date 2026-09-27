"""Run policy, public reads, atomicity and durable recovery with no providers."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_deployments import approved, deploy


def deployed(registry: tuple) -> dict:
    from worker import run_one

    revision, approval = approved(registry)
    response = deploy(registry, revision, approval)
    assert response.status_code == 202, response.text
    client, headers, engine, _ = registry
    assert run_one(sessionmaker(engine), str(uuid4()))
    return client.get(
        f"/api/v1/applications/{revision['application_id']}/deployments",
        headers=headers[2],
    ).json()["items"][0]


def submit(
    registry: tuple,
    deployment: dict,
    key: str = "run",
    actor: int = 2,
    **changes: object,
):
    client, headers, _, _ = registry
    return client.post(
        f"/api/v1/deployments/{deployment['id']}/runs",
        headers={**headers[actor], "Idempotency-Key": key},
        json={
            "resource_key": "synthetic_job",
            "execution_mode": "simulated",
            **changes,
        },
    )


def runs(registry: tuple, deployment: dict) -> list[dict]:
    client, headers, _, _ = registry
    response = client.get(
        f"/api/v1/deployments/{deployment['id']}/runs", headers=headers[2]
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_success_failure_history_and_replay(registry: tuple) -> None:
    from worker import run_one

    deployment = deployed(registry)
    client, headers, engine, _ = registry
    first = submit(registry, deployment, parameters={"row_count": 7})
    assert first.status_code == 202, first.text
    assert (
        submit(registry, deployment, parameters={"row_count": 7}).json() == first.json()
    )
    assert submit(registry, deployment, parameters={"row_count": 8}).status_code == 409
    assert submit(registry, deployment, "conflicting").status_code == 409
    assert runs(registry, deployment)[0]["status"] == "queued"
    assert run_one(sessionmaker(engine), "success")
    row = runs(registry, deployment)[0]
    assert row["status"] == "succeeded"
    assert row["result"] == {
        "execution_mode": "simulated",
        "lifecycle": "terminated",
        "outcome": "success",
        "output": {"rows": 7, "total": 21},
        "output_verified": True,
    }
    assert row["last_observed_at"].endswith("+00:00")
    assert row["provider_run_id"] is None
    assert (
        submit(registry, deployment, parameters={"row_count": 7}).json()["operation_id"]
        == first.json()["operation_id"]
    )
    assert (
        submit(registry, deployment, "failure", scenario="failure").status_code == 202
    )
    assert run_one(sessionmaker(engine), "failure")
    assert runs(registry, deployment)[1]["result"]["outcome"] == "failure"
    assert (
        client.get(f"/api/v1/deployments/{deployment['id']}", headers=headers[2]).json()
        == deployment
    )
    app_path = f"/api/v1/applications/{deployment['application_id']}"
    assert client.get(app_path + "/runs", headers=headers[2]).json()["items"] == runs(
        registry, deployment
    )
    # Regression: T06's deployment kind must also serialize in operation history.
    history = client.get(app_path + "/operations", headers=headers[2])
    assert history.status_code == 200, history.text
    assert {op["kind"] for op in history.json()["items"]} >= {
        "deploy_simulated",
        "run_simulated",
    }
    page = client.get(app_path + "/runs?limit=1", headers=headers[2]).json()
    second = client.get(
        app_path + "/runs",
        params={"limit": 1, "cursor": page["next_cursor"]},
        headers=headers[2],
    ).json()
    assert second["items"][0]["id"] != page["items"][0]["id"]
    for path in (
        f"/api/v1/runs/{row['id']}",
        app_path + "/runs",
        f"/api/v1/deployments/{deployment['id']}/runs",
    ):
        public = client.get(path, headers=headers[2])
        assert public.status_code == 200
        assert all(
            secret not in public.text
            for secret in ("storage_key", "artifact_dir", "password", "fencing_token")
        )
        assert client.get(path, headers=headers[5]).status_code == 404
        assert client.get(path).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"resource_key": "unknown"},
        {"execution_mode": "real"},
        {"scenario": "force_success"},
        {"parameters": {"row_count": 0}},
        {"parameters": {"row_count": 10001}},
        {"parameters": {"row_count": True}},
        {"parameters": {"row_count": "5"}},
        {"parameters": {"command": "do something"}},
        {"token": "do-not-echo-this"},
    ],
)
def test_closed_run_input(registry: tuple, changes: dict) -> None:
    deployment = deployed(registry)
    response = submit(registry, deployment, **changes)
    assert response.status_code == 422, response.text
    assert "do-not-echo-this" not in response.text
    assert runs(registry, deployment) == []


def test_operator_only_and_failed_or_missing_resource_denied(registry: tuple) -> None:
    from models.deployment import Deployment
    from models.platform import ApplicationRole
    from worker import run_one

    deployment = deployed(registry)
    client, headers, engine, _ = registry
    assert (
        submit(registry, deployment, actor=1).status_code == 403
    )  # Admin is not operator.
    assert submit(registry, deployment, actor=3).status_code == 403
    assert submit(registry, deployment, actor=5).status_code == 404
    with Session(engine) as db:
        db.execute(
            delete(ApplicationRole).where(
                ApplicationRole.user_id == 2, ApplicationRole.role == "developer"
            )
        )
        db.commit()
    assert (
        submit(registry, deployment).status_code == 202
    )  # Operator alone is sufficient.
    assert run_one(sessionmaker(engine), "operator-only")
    assert runs(registry, deployment)[0]["status"] == "succeeded"
    with Session(engine) as db:
        row = db.get(Deployment, UUID(deployment["id"]))
        row.status = "failed"
        db.commit()
    assert submit(registry, deployment, "failed-deployment").status_code == 409
    with Session(engine) as db:
        row = db.get(Deployment, UUID(deployment["id"]))
        row.status, row.resources = "succeeded", []
        db.commit()
    assert submit(registry, deployment, "missing-job").status_code == 409
    assert (
        client.post(
            f"/api/v1/deployments/{uuid4()}/runs",
            headers={**headers[2], "Idempotency-Key": "missing"},
            json={"resource_key": "synthetic_job", "execution_mode": "simulated"},
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "change", ["operator", "inactive", "archived", "binding", "disabled"]
)
def test_worker_rechecks_policy(registry: tuple, change: str) -> None:
    from models.database import User
    from models.platform import (
        Application,
        ApplicationRole,
        Environment,
        EnvironmentBinding,
    )
    from worker import run_one

    deployment = deployed(registry)
    _, _, engine, _ = registry
    assert submit(registry, deployment).status_code == 202
    with Session(engine) as db:
        binding = db.get(EnvironmentBinding, UUID(deployment["binding_id"]))
        if change == "operator":
            db.execute(
                delete(ApplicationRole).where(
                    ApplicationRole.user_id == 2, ApplicationRole.role == "operator"
                )
            )
        elif change == "inactive":
            db.get(User, 2).is_active = False
        elif change == "archived":
            db.get(
                Application, UUID(deployment["application_id"])
            ).lifecycle = "archived"
        elif change == "binding":
            binding.version += 1
        else:
            db.get(Environment, binding.environment_id).enabled = False
        db.commit()
    assert run_one(sessionmaker(engine), "revoked")
    from models.job_run import JobRun
    from models.operations import OperationReservation

    with Session(engine) as db:
        row = db.scalar(select(JobRun))
        assert row.status == "failed" and row.result is None
        assert db.get(OperationReservation, UUID(deployment["binding_id"])) is None


def test_cancel_retry_fence_and_reconcile(registry: tuple) -> None:
    from integrations.simulated_run import execute
    from models.job_run_schemas import RunInput
    from models.operations import Operation
    from models.platform import utcnow
    from services.queue_service import LostLease, claim, finish
    from worker import run_one

    deployment = deployed(registry)
    client, headers, engine, _ = registry
    operation = submit(registry, deployment).json()["operation_id"]
    path = f"/api/v1/operations/{operation}"
    assert (
        client.post(
            path + "/cancel", headers={**headers[2], "Idempotency-Key": "cancel"}
        ).status_code
        == 202
    )
    assert runs(registry, deployment)[0]["status"] == "cancelled"
    retry = client.post(
        path + "/retry", headers={**headers[2], "Idempotency-Key": "retry"}
    )
    assert retry.status_code == 202, retry.text
    retry_id = UUID(retry.json()["operation_id"])
    with Session(engine) as db:
        stale = claim(db, "stale")
        db.get(Operation, retry_id).lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        fresh = claim(db, "fresh")
        with pytest.raises(LostLease):
            finish(
                db,
                stale,
                "succeeded",
                run_result=execute(
                    RunInput(resource_key="synthetic_job", execution_mode="simulated")
                ),
            )
        finish(db, fresh, "safe_to_retry")
        db.get(Operation, retry_id).available_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert run_one(sessionmaker(engine), "recovered")
    rows = runs(registry, deployment)
    assert [r["status"] for r in rows] == ["cancelled", "succeeded"]
    assert (
        client.get(f"/api/v1/operations/{retry_id}", headers=headers[2]).json()[
            "retry_of"
        ]
        == operation
    )


def test_submission_and_completion_rollback(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from integrations.simulated_run import execute
    from models.job_run import JobRun
    from models.job_run_schemas import RunInput
    from models.operations import Operation, OperationReservation
    from services import audit_service
    from services.queue_service import claim, finish

    deployment = deployed(registry)
    _, _, engine, _ = registry
    original = audit_service.record_audit

    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(audit_service, "record_audit", fail)
    assert submit(registry, deployment).status_code == 500
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(JobRun)) == 0
        assert db.get(OperationReservation, UUID(deployment["binding_id"])) is None
    monkeypatch.setattr(audit_service, "record_audit", original)
    operation_id = UUID(submit(registry, deployment).json()["operation_id"])
    with Session(engine) as db:
        item = claim(db, "worker")
    monkeypatch.setattr(audit_service, "record_audit", fail)
    with Session(engine) as db:
        with pytest.raises(RuntimeError):
            finish(
                db,
                item,
                "succeeded",
                run_result=execute(
                    RunInput(resource_key="synthetic_job", execution_mode="simulated")
                ),
            )
    with Session(engine) as db:
        assert db.get(Operation, operation_id).status == "running"
        assert db.scalar(select(JobRun)).result is None
        assert db.get(OperationReservation, UUID(deployment["binding_id"])) is not None


@pytest.mark.parametrize("revoke", [True, False])
def test_completion_rechecks_authorization_and_output(
    registry: tuple, revoke: bool
) -> None:
    from integrations.simulated_run import execute
    from models.job_run_schemas import RunInput
    from models.platform import ApplicationRole
    from services.queue_service import claim, finish

    deployment = deployed(registry)
    _, _, engine, _ = registry
    assert submit(registry, deployment).status_code == 202
    result = execute(RunInput(resource_key="synthetic_job", execution_mode="simulated"))
    with Session(engine) as db:
        item = claim(db, "worker")
        if revoke:
            db.execute(
                delete(ApplicationRole).where(
                    ApplicationRole.user_id == 2, ApplicationRole.role == "operator"
                )
            )
            db.commit()
        else:
            result.output = {"rows": 100, "total": 0}
        finish(db, item, "succeeded", run_result=result)
    row = runs(registry, deployment)[0]
    assert row["status"] == "failed" and row["result"] is None


def test_uncertain_run_retains_reservation_after_revocation(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from integrations import simulated_run
    from models.platform import ApplicationRole
    from worker import run_one

    deployment = deployed(registry)
    client, headers, engine, _ = registry
    operation = submit(registry, deployment).json()["operation_id"]
    original = simulated_run.execute

    def unavailable(data):
        raise RuntimeError("unobserved handler result")

    monkeypatch.setattr(simulated_run, "execute", unavailable)
    assert run_one(sessionmaker(engine), "uncertain")
    assert runs(registry, deployment)[0]["status"] == "unknown"
    with Session(engine) as db:
        db.execute(
            delete(ApplicationRole).where(
                ApplicationRole.user_id == 2, ApplicationRole.role == "operator"
            )
        )
        db.commit()
    monkeypatch.setattr(simulated_run, "execute", original)
    assert run_one(sessionmaker(engine), "revoked-reconciler")
    path = f"/api/v1/operations/{operation}"
    assert client.get(path, headers=headers[2]).json()["status"] == "needs_attention"
    with Session(engine) as db:
        db.add(
            ApplicationRole(
                application_id=UUID(deployment["application_id"]),
                user_id=2,
                role="operator",
            )
        )
        db.commit()
    assert submit(registry, deployment, "conflict").status_code == 409
    assert (
        client.post(
            path + "/retry", headers={**headers[2], "Idempotency-Key": "unsafe"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/reconcile",
            headers={**headers[2], "Idempotency-Key": "observe"},
            json={"evidence": "Observe again after restoring operator"},
        ).status_code
        == 202
    )
    assert run_one(sessionmaker(engine), "reconciler")
    assert client.get(path, headers=headers[2]).json()["status"] == "retry_wait"
    assert runs(registry, deployment)[0]["result"] is None
    assert submit(registry, deployment, "still-reserved").status_code == 409
