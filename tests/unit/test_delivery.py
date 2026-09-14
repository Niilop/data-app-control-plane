"""Preparation behavior: integrity, authorization, transactions and recovery."""

import io
import stat
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_environments import bound


def submit(registry: tuple) -> tuple[dict, dict, dict]:
    client, headers, _, _ = registry
    app, _, binding = bound(registry)
    body = {
        "binding_id": binding["id"],
        "expected_binding_version": binding["version"],
        "parameters": {"package_name": "batch_test"},
    }
    response = client.post(
        f"/api/v1/applications/{app['id']}/generations",
        json=body,
        headers={**headers[2], "Idempotency-Key": "generate"},
    )
    assert response.status_code == 202, response.text
    assert response.json()["execution_mode"] == "offline"
    return app, binding, response.json()


def generated(registry: tuple) -> tuple[dict, dict, dict]:
    from worker import run_one

    app, binding, _ = submit(registry)
    assert run_one(sessionmaker(registry[2]), str(uuid4()))
    client, headers, _, _ = registry
    rows = client.get(
        f"/api/v1/applications/{app['id']}/generations", headers=headers[2]
    ).json()["items"]
    assert len(rows) == 1 and rows[0]["artifact_digest"]
    return app, binding, rows[0]


def revision(registry: tuple) -> dict:
    app, binding, generation = generated(registry)
    client, headers, _, _ = registry
    response = client.post(
        f"/api/v1/applications/{app['id']}/revisions",
        headers=headers[2],
        json={
            "generation_id": generation["id"],
            "binding_id": binding["id"],
            "expected_binding_version": binding["version"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_end_to_end_integrity_immutable_revision_and_offline_report(
    registry: tuple,
) -> None:
    from models.delivery import DeploymentRevision
    from worker import run_one

    client, headers, engine, _ = registry
    row = revision(registry)
    digest = row["artifact_digest"]
    response = client.get(f"/api/v1/artifacts/{digest}", headers=headers[2])
    from services.template_service import sha, unpack

    assert sha(response.content) == digest
    assert "manifest.json" in unpack(response.content)
    assert "storage" not in row
    with Session(engine) as db:
        saved = db.get(DeploymentRevision, UUID(row["id"]))
        saved.config_snapshot = {"changed": True}
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
    path = f"/api/v1/revisions/{row['id']}/validations"
    response = client.post(
        path,
        json={"scope": "offline"},
        headers={**headers[2], "Idempotency-Key": "validate"},
    )
    assert response.status_code == 202, response.text
    assert run_one(sessionmaker(engine), str(uuid4()))
    reports = client.get(path, headers=headers[2]).json()["items"]
    assert len(reports) == 1 and reports[0]["result"] == "passed"
    assert reports[0]["scope"] == "offline"
    report = client.get(
        f"/api/v1/artifacts/{reports[0]['report_digest']}", headers=headers[2]
    ).json()
    assert report["workspace_validated"] is False and report["code_executed"] is False
    assert (
        client.post(
            path,
            json={"scope": "workspace"},
            headers={**headers[2], "Idempotency-Key": "workspace"},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/revisions/{row['id']}",
            json={"config_snapshot": {}},
            headers=headers[2],
        ).status_code
        == 405
    )
    for path in (
        f"/api/v1/revisions/{row['id']}",
        f"/api/v1/artifacts/{digest}",
        f"/api/v1/revisions/{row['id']}/validations",
        f"/api/v1/artifacts/{reports[0]['report_digest']}",
    ):
        assert client.get(path, headers=headers[5]).status_code == 404
        assert client.get(path).status_code == 401


@pytest.mark.parametrize(
    "change", ["role", "inactive", "binding", "archived", "template"]
)
def test_worker_policy_changes_leave_no_artifact_association(
    registry: tuple, change: str
) -> None:
    from models.database import User
    from models.delivery import Generation, TemplateVersion
    from models.operations import Operation, OperationReservation
    from models.platform import Application, ApplicationRole, EnvironmentBinding
    from worker import run_one

    app, binding, accepted = submit(registry)
    engine = registry[2]
    with Session(engine) as db:
        if change == "role":
            db.execute(
                delete(ApplicationRole).where(ApplicationRole.role == "developer")
            )
        elif change == "inactive":
            db.get(User, 2).is_active = False
        elif change == "binding":
            db.get(EnvironmentBinding, UUID(binding["id"])).version += 1
        elif change == "archived":
            db.get(Application, UUID(app["id"])).lifecycle = "archived"
        else:
            db.get(TemplateVersion, "python-batch:1.0.0").active = False
        db.commit()
    assert run_one(sessionmaker(engine), str(uuid4()))
    with Session(engine) as db:
        assert db.get(Operation, UUID(accepted["operation_id"])).status == "failed"
        assert db.scalar(select(Generation)).artifact_digest is None
        assert db.scalar(select(func.count()).select_from(OperationReservation)) == 0


def test_idempotency_authorization_and_stale_capture(registry: tuple) -> None:
    from models.platform import EnvironmentBinding

    client, headers, engine, _ = registry
    app, binding, generation = generated(registry)
    path = f"/api/v1/applications/{app['id']}/generations"
    body = {
        "binding_id": binding["id"],
        "expected_binding_version": binding["version"],
        "parameters": {"package_name": "batch_test"},
    }
    keys = {**headers[2], "Idempotency-Key": "generate"}
    same = client.post(path, headers=keys, json=body)
    assert (
        same.status_code == 202
        and same.json()["operation_id"] == generation["operation_id"]
    )
    body["parameters"]["package_name"] = "batch_other"
    assert client.post(path, headers=keys, json=body).status_code == 409
    for actor in (1, 3, 4):
        assert (
            client.post(
                path, headers={**headers[actor], "Idempotency-Key": "denied"}, json=body
            ).status_code
            == 403
        )
    assert (
        client.post(
            path, headers={**headers[5], "Idempotency-Key": "denied"}, json=body
        ).status_code
        == 404
    )
    for parameters in (
        {"package_name": "../escape"},
        {"token": "secret"},
        {"package_name": "batch_a;bad"},
    ):
        body["parameters"] = parameters
        response = client.post(path, headers=keys, json=body)
        assert response.status_code == 422 and "secret" not in response.text
    with Session(engine) as db:
        db.get(EnvironmentBinding, UUID(binding["id"])).version += 1
        db.commit()
    response = client.post(
        f"/api/v1/applications/{app['id']}/revisions",
        headers=headers[2],
        json={
            "generation_id": generation["id"],
            "binding_id": binding["id"],
            "expected_binding_version": binding["version"],
        },
    )
    assert response.status_code == 409


def test_corrupt_artifact_download_and_failed_validation(registry: tuple) -> None:
    from services.delivery_service import store
    from worker import run_one

    client, headers, engine, _ = registry
    row = revision(registry)
    (store().root / row["artifact_digest"]).write_bytes(b"corrupt")
    assert (
        client.get(
            f"/api/v1/artifacts/{row['artifact_digest']}", headers=headers[2]
        ).status_code
        == 409
    )
    path = f"/api/v1/revisions/{row['id']}/validations"
    assert (
        client.post(
            path,
            headers={**headers[2], "Idempotency-Key": "v"},
            json={"scope": "offline"},
        ).status_code
        == 202
    )
    run_one(sessionmaker(engine), str(uuid4()))
    assert client.get(path, headers=headers[2]).json()["items"][0]["result"] == "failed"


def test_lost_lease_cannot_publish_related_result(registry: tuple) -> None:
    from models.delivery import Artifact, Generation
    from services.delivery_service import execute, store
    from services.queue_service import LostLease, claim, finish
    from test_operations import due

    _, _, accepted = submit(registry)
    engine = registry[2]
    with Session(engine) as db:
        item = claim(db, str(uuid4()))
        content, media, verdict = execute(db, item.operation_id)
    result = (store().put(content), len(content), media, verdict)
    due(engine, UUID(accepted["operation_id"]), expire=True)
    with Session(engine) as db:
        with pytest.raises(LostLease):
            finish(db, item, "succeeded", delivery_result=result)
        assert db.scalar(select(func.count()).select_from(Artifact)) == 0
        assert db.scalar(select(Generation)).artifact_digest is None
    from worker import run_one

    assert run_one(sessionmaker(engine), str(uuid4()))
    due(engine, item.operation_id)
    assert run_one(sessionmaker(engine), str(uuid4()))
    with Session(engine) as db:
        assert db.scalar(select(Generation)).artifact_digest == result[0]


def test_submission_audit_failure_rolls_back(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.delivery import Generation
    from models.operations import Operation, OperationCommand, OperationReservation
    from services import audit_service

    app, _, binding = bound(registry)

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("hidden secret")

    monkeypatch.setattr(audit_service, "record_audit", fail)
    response = registry[0].post(
        f"/api/v1/applications/{app['id']}/generations",
        headers={**registry[1][2], "Idempotency-Key": "rollback"},
        json={
            "binding_id": binding["id"],
            "expected_binding_version": binding["version"],
        },
    )
    assert response.status_code == 500 and "hidden secret" not in response.text
    with Session(registry[2]) as db:
        for model in (Generation, Operation, OperationCommand, OperationReservation):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_template_determinism_and_local_storage(tmp_path: Path) -> None:
    from integrations.artifact_store import ArtifactError, LocalArtifacts
    from models.delivery_schemas import TemplateParameters
    from services.template_service import render, sha, unpack

    one = render("test-app", "dev", {}, TemplateParameters())
    assert one == render("test-app", "dev", {}, TemplateParameters())
    assert one != render(
        "test-app", "dev", {}, TemplateParameters(package_name="batch_other")
    )
    assert len(unpack(one)) >= 8
    local = LocalArtifacts(tmp_path)
    digest = local.put(one)
    assert digest == sha(one) and LocalArtifacts(tmp_path).read(digest) == one
    assert local.put(one) == digest
    (tmp_path / digest).unlink()
    (tmp_path / digest).symlink_to(tmp_path / "outside")
    with pytest.raises(ArtifactError):
        local.read(digest)
    with pytest.raises(ArtifactError):
        local.read("../anything")


@pytest.mark.parametrize(
    "name", ["../escape", "/absolute", "a/../b", "a//b", "a\\b", "a/./b", "a:"]
)
def test_unsafe_archive_paths(name: str) -> None:
    from services.template_service import archive

    with pytest.raises(ValueError):
        archive({name: b"bad"})


@pytest.mark.parametrize("mode", [stat.S_IFLNK, stat.S_IFDIR])
def test_unsafe_archive_entries(mode: int) -> None:
    from services.template_service import unpack

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as output:
        entry = zipfile.ZipInfo("unsafe")
        entry.create_system = 3
        entry.external_attr = (mode | 0o644) << 16
        output.writestr(entry, b"target")
    with pytest.raises(ValueError):
        unpack(stream.getvalue())


def test_completion_rechecks_policy_and_atomic_audit(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.delivery import Artifact, Generation
    from models.operations import Operation
    from models.platform import ApplicationRole
    from services import audit_service
    from services.delivery_service import execute, store
    from services.queue_service import claim, finish

    _, _, accepted = submit(registry)
    engine = registry[2]
    with Session(engine) as db:
        item = claim(db, str(uuid4()))
        content, media, verdict = execute(db, item.operation_id)
    result = (store().put(content), len(content), media, verdict)
    real_audit = audit_service.record_audit

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(audit_service, "record_audit", fail)
    with Session(engine) as db:
        with pytest.raises(RuntimeError):
            finish(db, item, "succeeded", delivery_result=result)
        assert db.scalar(select(func.count()).select_from(Artifact)) == 0
        assert db.scalar(select(Generation)).artifact_digest is None
    monkeypatch.setattr(audit_service, "record_audit", real_audit)
    with Session(engine) as db:
        db.execute(delete(ApplicationRole).where(ApplicationRole.role == "developer"))
        db.commit()
        finish(db, item, "succeeded", delivery_result=result)
        assert db.get(Operation, UUID(accepted["operation_id"])).status == "failed"
        assert db.scalar(select(Generation)).artifact_digest is None


def test_cancel_retry_keeps_handler_and_requires_developer(registry: tuple) -> None:
    from models.platform import ApplicationRole
    from worker import run_one

    client, headers, engine, _ = registry
    app, _, accepted = submit(registry)
    with Session(engine) as db:
        db.add(
            ApplicationRole(application_id=UUID(app["id"]), user_id=2, role="operator")
        )
        db.commit()
    path = f"/api/v1/operations/{accepted['operation_id']}"
    keys = {**headers[2], "Idempotency-Key": "cancel"}
    assert client.post(path + "/cancel", headers=keys).json()["status"] == "cancelled"
    response = client.post(
        path + "/retry", headers={**headers[2], "Idempotency-Key": "retry"}
    )
    assert response.status_code == 202, response.text
    retry = client.get(
        f"/api/v1/operations/{response.json()['operation_id']}", headers=headers[2]
    ).json()
    assert retry["kind"] == "generate_bundle" and retry["execution_mode"] == "offline"
    assert retry["retry_of"] == accepted["operation_id"]
    assert run_one(sessionmaker(engine), str(uuid4()))
    rows = client.get(
        f"/api/v1/applications/{app['id']}/generations", headers=headers[2]
    ).json()["items"]
    assert len(rows) == 2 and sum(bool(g["artifact_digest"]) for g in rows) == 1
