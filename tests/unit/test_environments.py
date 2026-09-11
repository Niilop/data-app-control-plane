"""Environment authorization, safe configuration, versioning and atomic audit."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_registry import create


def environment_payload(**changes: object) -> dict:
    return {
        "name": "Local sandbox",
        "workspace_ref": "simulated://local-sandbox",
        "allowed_executor": "simulated",
        "allowed_bundle_targets": ["sandbox", "dev"],
        **changes,
    }


def create_environment(registry: tuple, **changes: object) -> dict:
    client, headers, _, _ = registry
    response = client.post(
        "/api/v1/environments", headers=headers[1], json=environment_payload(**changes)
    )
    assert response.status_code == 201, response.text
    assert response.headers["location"].endswith(response.json()["id"])
    return response.json()


def bound(registry: tuple) -> tuple[dict, dict, dict]:
    application = create(registry)
    environment = create_environment(registry)
    client, headers, _, _ = registry
    response = client.post(
        f"/api/v1/applications/{application['id']}/bindings",
        headers=headers[1],
        json={"environment_id": environment["id"], "bundle_target": "sandbox"},
    )
    assert response.status_code == 201, response.text
    return application, environment, response.json()


def test_binding_round_trip_visibility_and_admin_only_writes(registry: tuple) -> None:
    client, headers, _, _ = registry
    application, environment, binding = bound(registry)
    path = f"/api/v1/applications/{application['id']}/bindings"
    assert binding["version"] == 1
    assert binding["execution_mode"] == "simulated"
    assert binding["usable"] is True
    assert binding["environment"]["allow_self_approval"] is False
    assert binding["config"] == {
        "schema_version": 1,
        "synthetic_row_count": 100,
        "max_runtime_seconds": 300,
    }
    for actor in (1, 2, 3, 4):
        result = client.get(path, headers=headers[actor])
        assert result.status_code == 200
        assert result.json()["items"][0]["id"] == binding["id"]
        assert (
            client.get(path + f"/{binding['id']}", headers=headers[actor]).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/v1/environments/{environment['id']}", headers=headers[actor]
            ).status_code
            == 200
        )
    assert client.get(path, headers=headers[5]).status_code == 404
    assert client.get(path + f"/{binding['id']}", headers=headers[5]).status_code == 404
    assert client.get("/api/v1/environments", headers=headers[5]).json() == {
        "items": [],
        "next_cursor": None,
    }
    assert (
        client.get(
            f"/api/v1/environments/{environment['id']}", headers=headers[5]
        ).status_code
        == 404
    )
    assert client.get("/api/v1/environments").status_code == 401
    for actor in (2, 3, 4, 5, 6):
        assert (
            client.post(
                "/api/v1/environments",
                headers=headers[actor],
                json=environment_payload(name="Forbidden"),
            ).status_code
            == 403
        )
        assert (
            client.patch(
                f"/api/v1/environments/{environment['id']}",
                headers=headers[actor],
                json={"expected_version": 1, "enabled": False},
            ).status_code
            == 403
        )
        assert (
            client.post(
                path,
                headers=headers[actor],
                json={"environment_id": environment["id"], "bundle_target": "sandbox"},
            ).status_code
            == 403
        )
        assert (
            client.patch(
                path + f"/{binding['id']}",
                headers=headers[actor],
                json={"expected_version": 1, "bundle_target": "dev"},
            ).status_code
            == 403
        )
    audit = client.get(
        f"/api/v1/applications/{application['id']}/audit-events", headers=headers[2]
    ).json()["items"]
    assert audit[-1]["action"] == "binding.created"
    assert audit[-1]["actor_user_id"] == 1
    assert audit[-1]["details"]["execution_mode"] == "simulated"


@pytest.mark.parametrize(
    "changes",
    [
        {"workspace_ref": "https://user:secret@host.test"},
        {"workspace_ref": "https://adb-123.azuredatabricks.net"},
        {"workspace_ref": "simulated://../escape"},
        {"workspace_ref": "simulated://sandbox?token=secret"},
        {"allowed_executor": "github_actions"},
        {"token": "secret"},
        {"allowed_bundle_targets": []},
        {"allowed_bundle_targets": ["dev", "dev"]},
        {"allowed_bundle_targets": ["../escape"]},
        {"allow_self_approval": "true"},
    ],
)
def test_invalid_environment_inputs(registry: tuple, changes: dict) -> None:
    client, headers, _, _ = registry
    response = client.post(
        "/api/v1/environments", headers=headers[1], json=environment_payload(**changes)
    )
    assert response.status_code == 422, response.text
    assert "secret" not in response.text
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


@pytest.mark.parametrize(
    "config",
    [
        {"token": "secret"},
        {"password": "secret"},
        {"credentials": {"key": "secret"}},
        {"schema_version": 2},
        {"schema_version": True},
        {"synthetic_row_count": "secret"},
        {"synthetic_row_count": True},
        {"synthetic_row_count": 0},
        {"synthetic_row_count": 10001},
        {"max_runtime_seconds": 3601},
        {"command": "arbitrary command"},
    ],
)
def test_binding_configuration_is_closed_and_sanitized(
    registry: tuple, config: dict
) -> None:
    client, headers, _, _ = registry
    application, environment, binding = bound(registry)
    path = f"/api/v1/applications/{application['id']}/bindings"
    for method, url, data in (
        (
            "POST",
            path,
            {
                "environment_id": environment["id"],
                "bundle_target": "dev",
                "config": config,
            },
        ),
        (
            "PATCH",
            path + f"/{binding['id']}",
            {"expected_version": 1, "config": config},
        ),
    ):
        response = client.request(method, url, headers=headers[1], json=data)
        assert response.status_code == 422, response.text
        assert "secret" not in response.text
    assert client.get(path, headers=headers[1]).json()["items"][0]["version"] == 1


def test_conflicts_disabled_unknown_unapproved_and_archived(registry: tuple) -> None:
    client, headers, engine, _ = registry
    application, environment, binding = bound(registry)
    path = f"/api/v1/applications/{application['id']}/bindings"
    assert (
        client.post(
            "/api/v1/environments", headers=headers[1], json=environment_payload()
        ).status_code
        == 409
    )
    assert (
        client.post(
            path,
            headers=headers[1],
            json={"environment_id": environment["id"], "bundle_target": "dev"},
        ).status_code
        == 409
    )
    for environment_id, target, code in (
        (str(uuid4()), "dev", "invalid_environment"),
        (environment["id"], "prod", "unapproved_target"),
    ):
        response = client.post(
            path,
            headers=headers[1],
            json={"environment_id": environment_id, "bundle_target": target},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == code
    second = create(registry, "other")
    assert (
        client.patch(
            f"/api/v1/applications/{second['id']}/bindings/{binding['id']}",
            headers=headers[1],
            json={"expected_version": 1, "bundle_target": "dev"},
        ).status_code
        == 404
    )
    client.patch(
        f"/api/v1/environments/{environment['id']}",
        headers=headers[1],
        json={"expected_version": 1, "enabled": False},
    )
    response = client.post(
        path,
        headers=headers[1],
        json={"environment_id": environment["id"], "bundle_target": "dev"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "environment_disabled"
    assert (
        client.patch(
            path + f"/{binding['id']}",
            headers=headers[1],
            json={"expected_version": 2, "bundle_target": "dev"},
        ).json()["error"]["code"]
        == "environment_disabled"
    )
    from models.platform import Application

    with Session(engine) as db:
        db.get(Application, UUID(application["id"])).lifecycle = "archived"
        db.commit()
    assert (
        client.patch(
            path + f"/{binding['id']}",
            headers=headers[1],
            json={"expected_version": 2, "bundle_target": "dev"},
        ).json()["error"]["code"]
        == "application_archived"
    )


def test_policy_change_invalidates_bindings_and_audits_versions(
    registry: tuple,
) -> None:
    client, headers, _, _ = registry
    application, environment, binding = bound(registry)
    path = f"/api/v1/applications/{application['id']}/bindings/{binding['id']}"
    updated = client.patch(
        path,
        headers=headers[1],
        json={"expected_version": 1, "config": {"synthetic_row_count": 200}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert updated.json()["config"]["schema_version"] == 1
    assert (
        client.patch(
            path,
            headers=headers[1],
            json={"expected_version": 1, "bundle_target": "dev"},
        ).status_code
        == 409
    )
    policy = client.patch(
        f"/api/v1/environments/{environment['id']}",
        headers=headers[1],
        json={
            "expected_version": 1,
            "allow_self_approval": True,
            "allowed_bundle_targets": ["dev"],
        },
    )
    assert policy.status_code == 200, policy.text
    current = client.get(path, headers=headers[2]).json()
    assert current["version"] == 3
    assert current["environment"]["version"] == 2
    assert current["environment"]["allow_self_approval"] is True
    assert current["bundle_target"] == "sandbox"
    assert current["usable"] is False
    assert (
        client.patch(
            path,
            headers=headers[1],
            json={"expected_version": 2, "bundle_target": "dev"},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            path,
            headers=headers[1],
            json={"expected_version": 3, "bundle_target": "dev"},
        ).json()["usable"]
        is True
    )
    assert (
        client.patch(
            f"/api/v1/environments/{environment['id']}",
            headers=headers[1],
            json={"expected_version": 1, "enabled": False},
        ).status_code
        == 409
    )
    history = client.get(
        f"/api/v1/applications/{application['id']}/audit-events", headers=headers[2]
    ).json()["items"]
    event = next(
        row for row in history if row["action"] == "binding.environment_changed"
    )
    assert event["request_id"] == policy.headers["x-request-id"]
    assert event["details"]["environment_before"]["allow_self_approval"] is False
    assert event["details"]["environment_after"]["allow_self_approval"] is True


def test_environment_visibility_filtered_before_pagination(registry: tuple) -> None:
    client, headers, _, _ = registry
    create_environment(registry, name="Hidden first")
    _, visible, _ = bound(registry)
    create_environment(registry, name="Hidden last")
    result = client.get("/api/v1/environments?limit=1", headers=headers[2]).json()
    assert [row["id"] for row in result["items"]] == [visible["id"]]
    assert result["next_cursor"] is None
    result = client.get("/api/v1/environments?limit=1", headers=headers[1]).json()
    assert result["next_cursor"] is not None
    assert (
        client.get(
            "/api/v1/environments",
            headers=headers[2],
            params={"cursor": result["next_cursor"]},
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "action",
    ["create_environment", "create_binding", "update_binding", "update_environment"],
)
def test_transaction_failure_has_no_partial_changes(
    registry: tuple, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    client, headers, engine, _ = registry
    application, environment, binding = bound(registry)
    from models.platform import AuditEvent, Environment, EnvironmentBinding
    from services import audit_service

    other_application = (
        create(registry, "rollback") if action == "create_binding" else application
    )
    with Session(engine) as db:
        before_count = db.scalar(select(func.count()).select_from(AuditEvent))
    original = audit_service.record_audit

    def fail(*args: object, **kwargs: object) -> None:
        # Flush actual changes and audit, then fail to establish real rollback.
        original(*args, **kwargs)
        raise RuntimeError("private diagnostic")

    path = f"/api/v1/applications/{application['id']}/bindings"
    with monkeypatch.context() as patch:
        patch.setattr(audit_service, "record_audit", fail)
        if action == "create_environment":
            response = client.post(
                "/api/v1/environments",
                headers=headers[1],
                json=environment_payload(name="Rollback"),
            )
        elif action == "create_binding":
            response = client.post(
                f"/api/v1/applications/{other_application['id']}/bindings",
                headers=headers[1],
                json={"environment_id": environment["id"], "bundle_target": "dev"},
            )
        elif action == "update_binding":
            response = client.patch(
                path + f"/{binding['id']}",
                headers=headers[1],
                json={"expected_version": 1, "config": {"synthetic_row_count": 500}},
            )
        else:
            response = client.patch(
                f"/api/v1/environments/{environment['id']}",
                headers=headers[1],
                json={"expected_version": 1, "enabled": False},
            )
    assert response.status_code == 500, response.text
    assert "private diagnostic" not in response.text
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == before_count
        assert db.scalar(select(func.count()).select_from(Environment)) == 1
        assert db.scalar(select(func.count()).select_from(EnvironmentBinding)) == 1
        assert db.get(EnvironmentBinding, UUID(binding["id"])).version == 1
        assert (
            db.get(EnvironmentBinding, UUID(binding["id"])).config[
                "synthetic_row_count"
            ]
            == 100
        )
        assert db.get(Environment, UUID(environment["id"])).enabled is True
        assert db.get(Environment, UUID(environment["id"])).version == 1


def test_explicit_seed_is_repeatable_and_does_not_overwrite_policy(
    registry: tuple,
) -> None:
    from models.database import User
    from models.platform import AuditEvent
    from seed_sandbox import seed_sandbox
    from services.policy_service import PolicyError

    with Session(registry[2]) as db:
        admin = db.get(User, 1)
        environment = seed_sandbox(db, admin)
        assert environment.allow_self_approval is False
        identifier = environment.id
        assert seed_sandbox(db, admin).id == identifier
        with pytest.raises(PolicyError, match="Existing sandbox differs"):
            seed_sandbox(db, admin, allow_self_approval=True)
        with pytest.raises(PolicyError, match="administrator"):
            seed_sandbox(db, db.get(User, 2))
        events = list(
            db.scalars(
                select(AuditEvent).where(AuditEvent.action == "environment.created")
            )
        )
        assert len(events) == 1
        assert events[0].actor_user_id == 1
        assert events[0].details["execution_mode"] == "simulated"
