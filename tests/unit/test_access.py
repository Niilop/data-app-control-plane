"""Access privacy, current authorization, atomic grants and archival boundaries."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from test_registry import create


def request(registry: tuple, app_id: str, user: int = 5, role: str = "viewer") -> dict:
    client, headers, _, _ = registry
    response = client.post(
        f"/api/v1/applications/{app_id}/access-requests",
        headers=headers[user],
        json={"requested_role": role, "reason": "Need to inspect results"},
    )
    assert response.status_code == 201, response.text
    assert (
        response.headers["location"]
        == f"/api/v1/access-requests/{response.json()['id']}"
    )
    return response.json()


def test_outsider_request_privacy_pagination_and_own_outcomes(registry: tuple) -> None:
    client, headers, _, _ = registry
    app = create(registry)
    path = f"/api/v1/applications/{app['id']}"
    first = request(registry, app["id"])
    other = request(registry, app["id"], user=4)
    second = request(registry, app["id"], role="operator")
    assert {"name", "repository_url", "owner_user_id", "description"}.isdisjoint(first)
    assert first["requested_by"] == 5
    for suffix in ("", "/roles", "/audit-events", "/capabilities"):
        assert client.get(path + suffix, headers=headers[5]).status_code == 404
    response = client.get(path + "/access-requests?limit=1", headers=headers[5]).json()
    assert [r["id"] for r in response["items"]] == [first["id"]]
    more = client.get(
        path + "/access-requests",
        headers=headers[5],
        params={"cursor": response["next_cursor"]},
    ).json()
    assert [r["id"] for r in more["items"]] == [second["id"]]
    assert (
        client.get(path + "/access-requests", headers=headers[2]).json()["items"] == []
    )
    assert (
        len(client.get(path + "/access-requests", headers=headers[3]).json()["items"])
        == 3
    )
    assert (
        client.get(
            f"/api/v1/access-requests/{other['id']}", headers=headers[5]
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/applications/{uuid4()}/access-requests", headers=headers[5]
        ).json()["items"]
        == []
    )
    assert (
        client.get("/api/v1/access-requests", headers=headers[1]).json()["items"] == []
    )
    assert (
        len(client.get("/api/v1/access-requests", headers=headers[5]).json()["items"])
        == 2
    )
    assert client.get(path + "/access-requests", headers=headers[6]).status_code == 403


@pytest.mark.parametrize(
    "changes",
    [
        {"requested_by": 2},
        {"user_id": 2},
        {"status": "approved"},
        {"requested_role": "platform_admin"},
        {"reason": " "},
        {"reason": "x" * 2001},
    ],
)
def test_closed_request_input(registry: tuple, changes: dict) -> None:
    client, headers, _, _ = registry
    app = create(registry)
    result = client.post(
        f"/api/v1/applications/{app['id']}/access-requests",
        headers=headers[5],
        json={"requested_role": "viewer", "reason": "Needed", **changes},
    )
    assert result.status_code == 422
    assert (
        client.get("/api/v1/access-requests", headers=headers[5]).json()["items"] == []
    )


def test_approval_current_manager_and_replay_never_regrants(registry: tuple) -> None:
    from models.access import AccessRequest
    from models.platform import ApplicationRole, AuditEvent

    client, headers, engine, _ = registry
    app = create(registry)
    path = f"/api/v1/applications/{app['id']}"
    row = request(registry, app["id"])
    assert request(registry, app["id"])["id"] == row["id"]
    assert (
        client.post(
            path + "/access-requests",
            headers=headers[5],
            json={"requested_role": "viewer", "reason": "Changed"},
        ).status_code
        == 409
    )
    decision = f"/api/v1/access-requests/{row['id']}/decision"
    data = {"decision": "approved", "reason": "Approved for review"}
    for user in (2, 4, 5):
        assert client.post(decision, headers=headers[user], json=data).status_code in (
            403,
            404,
        )
    approved = client.post(decision, headers=headers[3], json=data)
    assert approved.status_code == 200, approved.text
    assert approved.json()["decided_at"].endswith("+00:00")
    assert client.get(path, headers=headers[5]).status_code == 200
    assert (
        client.post(decision, headers=headers[3], json=data).json() == approved.json()
    )
    assert (
        client.post(
            decision, headers=headers[3], json={**data, "decision": "rejected"}
        ).status_code
        == 409
    )
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AccessRequest)) == 1
        grant = db.scalar(select(ApplicationRole).where(ApplicationRole.user_id == 5))
        grant_id = grant.id
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "access.approved")
            )
            == 1
        )
    assert (
        client.delete(f"{path}/roles/{grant_id}", headers=headers[3]).status_code == 204
    )
    assert client.post(decision, headers=headers[3], json=data).status_code == 200
    assert client.get(path, headers=headers[5]).status_code == 404
    assert (
        client.get(f"/api/v1/access-requests/{row['id']}", headers=headers[5]).json()[
            "status"
        ]
        == "approved"
    )


@pytest.mark.parametrize("user", [1, 3])
def test_independently_authorized_self_approval(registry: tuple, user: int) -> None:
    client, headers, _, _ = registry
    app = create(registry)
    row = request(registry, app["id"], user=user, role="operator")
    result = client.post(
        f"/api/v1/access-requests/{row['id']}/decision",
        headers=headers[user],
        json={"decision": "approved", "reason": "Local operator"},
    )
    assert result.status_code == 200


def test_rejection_withdrawal_and_inactive_subject(registry: tuple) -> None:
    from models.database import User

    client, headers, engine, _ = registry
    app = create(registry)
    row = request(registry, app["id"])
    path = f"/api/v1/access-requests/{row['id']}"
    assert client.post(path + "/cancel", headers=headers[3]).status_code == 403
    assert (
        client.post(path + "/cancel", headers=headers[5]).json()["status"]
        == "cancelled"
    )
    assert client.post(path + "/cancel", headers=headers[5]).status_code == 200
    row = request(registry, app["id"])
    path = f"/api/v1/access-requests/{row['id']}"
    with Session(engine) as db:
        db.get(User, 5).is_active = False
        db.commit()
    assert (
        client.post(
            path + "/decision",
            headers=headers[3],
            json={"decision": "approved", "reason": "Yes"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            path + "/decision",
            headers=headers[3],
            json={"decision": "rejected", "reason": "Account inactive"},
        ).status_code
        == 200
    )


@pytest.mark.parametrize("action", ["request", "approve", "archive"])
def test_transaction_failure_rolls_back_request_grant_and_archive(
    registry: tuple, monkeypatch, action: str
) -> None:
    from models.access import AccessRequest
    from models.platform import Application, ApplicationRole
    from services import access_service

    client, headers, engine, _ = registry
    app = create(registry)
    row = request(registry, app["id"]) if action != "request" else None

    def fail(*args, **kwargs):
        raise RuntimeError("Injected audit failure")

    monkeypatch.setattr(access_service, "record_audit", fail)
    path = f"/api/v1/applications/{app['id']}"
    if action == "request":
        result = client.post(
            path + "/access-requests",
            headers=headers[5],
            json={"requested_role": "viewer", "reason": "Need"},
        )
    elif action == "approve":
        result = client.post(
            f"/api/v1/access-requests/{row['id']}/decision",
            headers=headers[3],
            json={"decision": "approved", "reason": "Yes"},
        )
    else:
        result = client.post(
            path + "/archive", headers=headers[3], json={"expected_version": 1}
        )
    assert result.status_code == 500
    with Session(engine) as db:
        assert db.get(Application, UUID(app["id"])).lifecycle == "registered"
        assert (
            db.scalar(select(ApplicationRole).where(ApplicationRole.user_id == 5))
            is None
        )
        if row:
            assert db.get(AccessRequest, UUID(row["id"])).status == "pending"
        else:
            assert db.scalar(select(func.count()).select_from(AccessRequest)) == 0


def test_effective_access_explains_every_source_and_revocation_blocks_worker(
    registry: tuple,
) -> None:
    from models.operations import Operation, QueueProbe
    from test_operations import queued
    from worker import run_one

    client, headers, engine, team_id = registry
    operation_id = queued(registry)
    with Session(engine) as db:
        app_id = db.get(Operation, operation_id).application_id
    path = f"/api/v1/applications/{app_id}"
    team_role = client.post(
        path + "/roles",
        headers=headers[3],
        json={"team_id": team_id, "role": "operator"},
    ).json()
    assert (
        client.get(path + "/effective-access/3", headers=headers[2]).status_code == 403
    )
    access = client.get(path + "/effective-access/2", headers=headers[2]).json()
    assert len([g for g in access["grants"] if g["role"] == "operator"]) == 2
    direct_roles = client.get(path + "/roles", headers=headers[3]).json()["items"]
    for role in direct_roles:
        if role["user_id"] == 2:
            assert (
                client.delete(
                    path + f"/roles/{role['id']}", headers=headers[3]
                ).status_code
                == 204
            )
    retained = client.get(path + "/effective-access/2", headers=headers[3]).json()
    assert retained["can_read"] and retained["roles"] == ["operator"]
    assert retained["grants"][0]["team_id"] == team_id
    assert (
        client.delete(
            path + f"/roles/{team_role['id']}", headers=headers[3]
        ).status_code
        == 204
    )
    access = client.get(path + "/effective-access/2", headers=headers[3]).json()
    assert not access["can_read"] and access["grants"] == []
    assert client.get(path, headers=headers[2]).status_code == 404
    assert run_one(sessionmaker(engine), "revoked-worker")
    with Session(engine) as db:
        assert db.get(Operation, operation_id).status == "failed"
        assert db.scalar(select(QueueProbe)).result != "success"
    for user, relationship in (
        (1, "platform_admin"),
        (3, "application_owner"),
        (4, "data_owner"),
    ):
        access = client.get(
            path + f"/effective-access/{user}", headers=headers[3]
        ).json()
        assert access["can_read"] and relationship in access["relationships"]


def test_archive_version_policy_pending_requests_and_preservation(
    registry: tuple,
) -> None:
    client, headers, _, _ = registry
    app = create(registry)
    row = request(registry, app["id"])
    path = f"/api/v1/applications/{app['id']}"
    for user in (2, 4, 5):
        assert client.post(
            path + "/archive", headers=headers[user], json={"expected_version": 1}
        ).status_code in (403, 404)
    assert (
        client.post(
            path + "/archive", headers=headers[3], json={"expected_version": 2}
        ).status_code
        == 409
    )
    result = client.post(
        path + "/archive", headers=headers[3], json={"expected_version": 1}
    )
    assert result.status_code == 200, result.text
    assert result.json()["lifecycle"] == "archived" and result.json()["version"] == 2
    assert (
        client.get(path, headers=headers[2]).json()["repository_url"]
        == app["repository_url"]
    )
    assert (
        client.get(f"/api/v1/access-requests/{row['id']}", headers=headers[5]).json()[
            "status"
        ]
        == "cancelled"
    )
    assert client.get(path, headers=headers[5]).status_code == 404
    assert (
        client.post(
            path + "/access-requests",
            headers=headers[5],
            json={"requested_role": "viewer", "reason": "Need"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/roles", headers=headers[3], json={"user_id": 5, "role": "viewer"}
        ).status_code
        == 409
    )
    assert (
        client.patch(
            path, headers=headers[2], json={"expected_version": 2, "name": "Changed"}
        ).status_code
        == 409
    )
    caps = client.get(path + "/capabilities", headers=headers[2]).json()
    assert not any(caps.values())
    assert (
        len(client.get(path + "/audit-events", headers=headers[3]).json()["items"]) == 4
    )


@pytest.mark.parametrize(
    "status",
    ["queued", "running", "retry_wait", "reconciling", "needs_attention", "failed"],
)
def test_archive_rejects_unresolved_operations_or_retained_reservations(
    registry: tuple, status: str
) -> None:
    from models.operations import Operation
    from test_operations import queued

    client, headers, engine, _ = registry
    identifier = queued(registry)
    with Session(engine) as db:
        operation = db.get(Operation, identifier)
        app_id = operation.application_id
        operation.status = status
        db.commit()
    response = client.post(
        f"/api/v1/applications/{app_id}/archive",
        headers=headers[3],
        json={"expected_version": 1},
    )
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "unresolved_work"
    )


def test_archived_delivery_preserves_results_and_rejects_commands(
    registry: tuple,
) -> None:
    from test_job_runs import deployed, runs, submit
    from worker import run_one

    client, headers, engine, _ = registry
    deployment = deployed(registry)
    assert submit(registry, deployment).status_code == 202
    assert run_one(sessionmaker(engine), "before-archive")
    run = runs(registry, deployment)[0]
    path = f"/api/v1/applications/{deployment['application_id']}"
    app = client.get(path, headers=headers[3]).json()
    revision_path = f"/api/v1/revisions/{deployment['revision_id']}"
    revision = client.get(revision_path, headers=headers[2]).json()
    history = {
        suffix: client.get(path + suffix, headers=headers[2]).json()
        for suffix in ("/revisions", "/deployments", "/runs", "/operations")
    }
    artifact = client.get(
        f"/api/v1/artifacts/{revision['artifact_digest']}", headers=headers[2]
    )
    assert artifact.status_code == 200
    assert (
        client.post(
            path + "/archive",
            headers=headers[3],
            json={"expected_version": app["version"]},
        ).status_code
        == 200
    )
    for suffix, before in history.items():
        assert client.get(path + suffix, headers=headers[2]).json() == before
    assert (
        client.get(
            f"/api/v1/artifacts/{revision['artifact_digest']}", headers=headers[2]
        ).content
        == artifact.content
    )
    assert submit(registry, deployment, "new-after-archive").status_code == 409
    assert submit(registry, deployment, "run").status_code == 409
    assert (
        client.post(
            revision_path + "/validations",
            headers={**headers[2], "Idempotency-Key": "after-archive"},
            json={"scope": "offline"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/deployments",
            headers={**headers[2], "Idempotency-Key": "after-archive"},
            json={
                "revision_id": deployment["revision_id"],
                "approval_id": deployment["approval_id"],
                "binding_id": deployment["binding_id"],
                "execution_mode": "simulated",
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/operations/{run['operation_id']}/retry",
            headers={**headers[2], "Idempotency-Key": "after-archive"},
        ).status_code
        == 409
    )
    binding = client.get(path + "/bindings", headers=headers[1]).json()["items"][0]
    assert not binding["usable"]
    assert (
        client.patch(
            path + f"/bindings/{binding['id']}",
            headers=headers[1],
            json={
                "expected_version": binding["version"],
                "bundle_target": binding["bundle_target"],
            },
        ).status_code
        == 409
    )
