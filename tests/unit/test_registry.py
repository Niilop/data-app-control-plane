"""Offline API behavior using SQLite; PostgreSQL semantics have separate tests."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def payload(team_id: str, slug: str = "sales") -> dict:
    return {
        "slug": slug,
        "name": "Sales",
        "description": "Synthetic data",
        "owning_team_id": team_id,
        "owner_user_id": 3,
        "data_owner_user_id": 4,
        "repository_url": "https://github.com/example/sales.git",
        "bundle_root": "bundles/sales",
    }


def create(registry: tuple, slug: str = "sales") -> dict:
    client, headers, _, team_id = registry
    response = client.post(
        "/api/v1/applications", headers=headers[2], json=payload(team_id, slug)
    )
    assert response.status_code == 201, response.text
    assert response.headers["location"].endswith(response.json()["id"])
    return response.json()


def test_registration_roles_history_and_visibility(registry: tuple) -> None:
    client, headers, engine, _ = registry
    application = create(registry)
    path = f"/api/v1/applications/{application['id']}"
    assert application["version"] == 1
    assert application["lifecycle"] == "registered"
    assert application["repository_verified_at"] is None
    assert application["repository_url"] == "https://github.com/example/sales"
    assert application["created_by"] == 2
    assert application["created_at"].endswith("+00:00")
    for actor in (1, 2, 3, 4):
        assert client.get(path, headers=headers[actor]).status_code == 200
        assert (
            len(
                client.get("/api/v1/applications", headers=headers[actor]).json()[
                    "items"
                ]
            )
            == 1
        )
        roles = client.get(path + "/roles", headers=headers[actor]).json()["items"]
        assert {(row["user_id"], row["role"]) for row in roles} == {
            (2, "developer"),
            (2, "viewer"),
        }
    for suffix in ("", "/roles", "/audit-events"):
        assert client.get(path + suffix, headers=headers[5]).status_code == 404
    assert client.get("/api/v1/applications", headers=headers[5]).json() == {
        "items": [],
        "next_cursor": None,
    }
    audit = client.get(path + "/audit-events", headers=headers[3]).json()["items"]
    assert audit[0]["action"] == "application.registered"
    assert audit[0]["actor_user_id"] == 2
    assert audit[0]["details"]["owner_user_id"] == 3
    assert audit[0]["details"]["initial_roles"] == ["developer", "viewer"]
    from models.platform import Application

    with Session(engine) as db:
        assert db.get(Application, UUID(application["id"])).owning_team_id == UUID(
            registry[3]
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"repository_url": "https://user:secret@github.com/org/repo"},
        {"repository_url": "https://evil.test/org/repo"},
        {"repository_url": "https://github.com/org/repo?token=secret"},
        {"repository_url": "https://github.com/org/.."},
        {"repository_url": "https://github.com/org/repo\n"},
        {"bundle_root": "../escape"},
        {"bundle_root": "/absolute"},
        {"bundle_root": "a//b"},
        {"bundle_root": "a/./b"},
        {"bundle_root": "a\\b"},
        {"bundle_root": "%2e%2e/x"},
        {"slug": "Invalid Slug"},
        {"slug": "bad\n"},
        {"owner_user_id": 999},
        {"data_owner_user_id": 6},
        {"owning_team_id": str(uuid4())},
        {"is_platform_admin": True},
        {"repository_verified_at": "2026-01-01T00:00:00Z"},
    ],
)
def test_invalid_registration_is_sanitized(registry: tuple, changes: dict) -> None:
    client, headers, _, team_id = registry
    response = client.post(
        "/api/v1/applications", headers=headers[2], json={**payload(team_id), **changes}
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
    assert "secret" not in response.text
    assert client.get("/api/v1/applications", headers=headers[2]).json()["items"] == []


def test_duplicate_and_versioned_policy_updates(registry: tuple) -> None:
    client, headers, _, team_id = registry
    application = create(registry)
    path = f"/api/v1/applications/{application['id']}"
    assert (
        client.post(
            "/api/v1/applications", headers=headers[2], json=payload(team_id)
        ).status_code
        == 409
    )
    assert (
        client.patch(
            path, headers=headers[4], json={"expected_version": 1, "name": "No"}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            path, headers=headers[2], json={"expected_version": 1, "owner_user_id": 2}
        ).status_code
        == 403
    )
    updated = client.patch(
        path, headers=headers[2], json={"expected_version": 1, "name": "Updated"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    stale = client.patch(
        path, headers=headers[2], json={"expected_version": 1, "name": "Stale"}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_version"
    assert (
        client.patch(
            path, headers=headers[3], json={"expected_version": 2, "owner_user_id": 5}
        ).status_code
        == 200
    )
    assert client.get(path, headers=headers[3]).status_code == 404
    events = client.get(path + "/audit-events", headers=headers[5]).json()["items"]
    assert [row["actor_user_id"] for row in events] == [2, 2, 3]
    assert events[1]["request_id"] == updated.headers["x-request-id"]
    assert events[1]["details"]["before"] == {"name": "Sales"}
    assert client.get(path, headers=headers[2]).json()["name"] == "Updated"


def test_roles_team_revocation_and_no_inheritance(registry: tuple) -> None:
    client, headers, _, team_id = registry
    application = create(registry)
    path = f"/api/v1/applications/{application['id']}"
    for actor, status in ((2, 403), (4, 403), (5, 404)):
        assert (
            client.post(
                path + "/roles",
                headers=headers[actor],
                json={"user_id": 5, "role": "viewer"},
            ).status_code
            == status
        )
    for data in (
        {"user_id": 5, "role": "platform_admin"},
        {"role": "viewer"},
        {"user_id": 5, "team_id": team_id, "role": "viewer"},
    ):
        assert (
            client.post(path + "/roles", headers=headers[3], json=data).status_code
            == 422
        )
    assignment = client.post(
        path + "/roles",
        headers=headers[3],
        json={"team_id": team_id, "role": "operator"},
    )
    assert assignment.status_code == 201
    assert (
        client.post(
            path + "/roles",
            headers=headers[3],
            json={"team_id": team_id, "role": "operator"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/teams/{team_id}/members", headers=headers[1], json={"user_id": 5}
        ).status_code
        == 201
    )
    assert client.get(path, headers=headers[5]).status_code == 200
    assert (
        client.patch(
            path, headers=headers[5], json={"expected_version": 1, "name": "Forbidden"}
        ).status_code
        == 403
    )
    direct = client.post(
        path + "/roles", headers=headers[3], json={"user_id": 5, "role": "viewer"}
    ).json()
    assert (
        client.delete(
            f"/api/v1/teams/{team_id}/members/5", headers=headers[1]
        ).status_code
        == 204
    )
    assert client.get(path, headers=headers[5]).status_code == 200
    assert (
        client.delete(path + f"/roles/{direct['id']}", headers=headers[3]).status_code
        == 204
    )
    assert client.get(path, headers=headers[5]).status_code == 404
    assert client.get("/api/v1/teams", headers=headers[5]).json()["items"] == []
    assert (
        client.get(f"/api/v1/teams/{team_id}/members", headers=headers[5]).status_code
        == 404
    )
    audit = client.get("/api/v1/audit-events", headers=headers[1]).json()["items"]
    assert any(
        row["action"] == "team.member_removed" and row["actor_user_id"] == 1
        for row in audit
    )
    assert client.get("/api/v1/audit-events", headers=headers[2]).status_code == 403


def test_auth_admin_and_membership_boundaries(registry: tuple) -> None:
    client, headers, engine, team_id = registry
    assert client.get("/api/v1/applications").status_code == 401
    assert (
        client.post(
            "/api/v1/applications", headers=headers[1], json=payload(team_id)
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/teams", headers=headers[2], json={"name": "Unauthorized"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/teams/{team_id}/members", headers=headers[2], json={"user_id": 5}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/applications", headers=headers[6]).status_code == 403
    from models.database import User

    with Session(engine) as db:
        db.get(User, 2).is_active = False
        db.commit()
    assert client.get("/api/v1/applications", headers=headers[2]).status_code == 403
    assert client.get("/auth/me", headers=headers[2]).status_code == 403
    for field in ("is_active", "is_platform_admin"):
        response = client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "username": "new",
                "password": "private",
                field: True,
            },
        )
        assert response.status_code == 422
        assert "private" not in response.text


def test_permission_filtered_keyset_pagination(registry: tuple) -> None:
    client, headers, engine, _ = registry
    from models.platform import Application

    apps = [create(registry, f"sales-{i}") for i in range(4)]
    # Equal timestamps exercise the UUID tie-breaker; hide alternating records.
    with Session(engine) as db:
        rows = list(db.scalars(select(Application)))
        for index, row in enumerate(rows):
            row.created_at = rows[0].created_at
            if index % 2:
                row.data_owner_user_id = 3
        db.commit()
    seen = []
    cursor = None
    while True:
        params = {"limit": 1}
        if cursor:
            params["cursor"] = cursor
        response = client.get("/api/v1/applications", headers=headers[4], params=params)
        assert response.status_code == 200, response.text
        result = response.json()
        seen.extend(row["id"] for row in result["items"])
        cursor = result["next_cursor"]
        if cursor is None:
            break
        assert len(seen) < 4
    assert set(seen) == {apps[0]["id"], apps[2]["id"]}
    assert len(seen) == 2
    first = client.get("/api/v1/applications?limit=1", headers=headers[2]).json()
    for params in (
        {"limit": 0},
        {"limit": 101},
        {"cursor": "invalid!"},
        {"cursor": first["next_cursor"]},
    ):
        # Last cursor is valid structurally but belongs to another actor.
        response = client.get("/api/v1/applications", headers=headers[4], params=params)
        assert response.status_code == 422


@pytest.mark.parametrize("failure", ["audit", "commit"])
def test_registration_transaction_rolls_back(
    registry: tuple, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    client, headers, engine, team_id = registry
    from models.platform import Application, ApplicationRole, AuditEvent
    from services import audit_service

    def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("secret connection diagnostic")

    with monkeypatch.context() as patch:
        if failure == "audit":
            patch.setattr(audit_service, "record_audit", fail)
        else:
            patch.setattr(Session, "commit", fail)
        response = client.post(
            "/api/v1/applications", headers=headers[2], json=payload(team_id)
        )
    assert response.status_code == 500
    assert "secret" not in response.text
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Application)) == 0
        assert db.scalar(select(func.count()).select_from(ApplicationRole)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "application.registered")
            )
            == 0
        )


def test_bootstrap_and_compatible_login(registry: tuple) -> None:
    client, _, engine, _ = registry
    from bootstrap import bootstrap_account
    from models.platform import AuditEvent
    from models.schemas import UserCreate

    data = UserCreate(
        email="local@example.com", username="local", password="explicit-test-password"
    )
    with Session(engine) as db:
        user = bootstrap_account(db, data, admin=True)
        assert user.is_platform_admin
        user_id = user.id
        with pytest.raises(ValueError):
            bootstrap_account(db, data, admin=False)
        event = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "user.bootstrapped")
        )
        assert event.actor_kind == "local_bootstrap"
        assert event.actor_user_id is None
        assert event.target_id == str(user_id)
        assert "password" not in str(event.details)
    for identifier in ("local", "local@example.com"):
        response = client.post(
            "/auth/login", data={"username": identifier, "password": data.password}
        )
        assert response.status_code == 200, response.text
        profile = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer " + response.json()["access_token"]},
        ).json()
        assert profile["is_platform_admin"] is True
        assert "password_hash" not in profile
    response = client.post(
        "/auth/register",
        json={
            "email": "public@example.com",
            "username": "public",
            "password": "explicit-test-password",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_platform_admin"] is False


def test_registration_rejects_password_truncation(registry: tuple) -> None:
    client = registry[0]
    response = client.post(
        "/auth/register",
        json={
            "email": "unicode@example.com",
            "username": "unicode",
            "password": "é" * 40,
        },
    )
    assert response.status_code == 422
    assert "é" not in response.text
