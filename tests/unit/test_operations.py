"""Queue state machine, API authorization, atomicity and sanitized diagnostics."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_environments import bound


def queued(registry: tuple, scenario: str = "success") -> UUID:
    from models.database import User
    from models.operation_schemas import ProbeInput
    from models.platform import ApplicationRole
    from services.operation_service import create_probe

    application, _, binding = bound(registry)
    with Session(registry[2]) as db:
        db.add(
            ApplicationRole(
                application_id=UUID(application["id"]), user_id=2, role="operator"
            )
        )
        db.commit()
        return create_probe(
            db,
            db.get(User, 2),
            UUID(application["id"]),
            UUID(binding["id"]),
            ProbeInput(scenario=scenario),
            "submit",
            str(uuid4()),
        ).id


def due(engine: object, operation_id: UUID, *, expire: bool = False) -> None:
    from models.operations import Operation
    from models.platform import utcnow

    with Session(engine) as db:
        operation = db.get(Operation, operation_id)
        operation.available_at = utcnow() - timedelta(seconds=1)
        if expire:
            operation.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()


def test_api_visibility_cancellation_retry_and_idempotency(registry: tuple) -> None:
    from models.operations import Operation, QueueProbe
    from services.queue_service import claim

    client, headers, engine, _ = registry
    identifier = queued(registry)
    path = f"/api/v1/operations/{identifier}"
    for actor in (1, 2, 3, 4):
        response = client.get(path, headers=headers[actor])
        assert response.status_code == 200
        assert response.json()["execution_mode"] == "simulated"
        assert not {"payload", "worker_id", "fencing_token"} & response.json().keys()
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers[5]).status_code == 404
    assert client.get(path + "/attempts", headers=headers[5]).status_code == 404
    assert client.post(path + "/cancel", headers=headers[2]).status_code == 422
    for actor in (1, 3, 4):
        assert (
            client.post(
                path + "/cancel", headers={**headers[actor], "Idempotency-Key": "c"}
            ).status_code
            == 403
        )
    keys = {**headers[2], "Idempotency-Key": "cancel"}
    response = client.post(path + "/cancel", headers=keys)
    assert response.status_code == 202
    assert response.json()["status"] == "cancelled"
    assert response.headers["location"] == path
    assert client.post(path + "/cancel", headers=keys).json() == response.json()
    with Session(engine) as db:
        assert claim(db, str(uuid4())) is None
    keys["Idempotency-Key"] = "retry"
    retry = client.post(path + "/retry", headers=keys)
    assert retry.status_code == 202
    assert retry.json()["operation_id"] != str(identifier)
    assert client.post(path + "/retry", headers=keys).json() == retry.json()
    with Session(engine) as db:
        newer = db.get(Operation, UUID(retry.json()["operation_id"]))
        assert newer.retry_of == identifier
        assert db.scalar(select(func.count()).select_from(QueueProbe)) == 2


def test_submission_replay_conflict_and_transaction_rollback(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.database import User
    from models.operation_schemas import ProbeInput
    from models.operations import (
        Operation,
        OperationCommand,
        OperationReservation,
        QueueProbe,
    )
    from models.platform import AuditEvent
    from services import audit_service
    from services.operation_service import create_probe
    from services.policy_service import PolicyError

    identifier = queued(registry)
    with Session(registry[2]) as db:
        operation = db.get(Operation, identifier)
        app_id, binding_id = operation.application_id, operation.binding_id
        actor = db.get(User, 2)
        assert (
            create_probe(
                db, actor, app_id, binding_id, ProbeInput(), "submit", str(uuid4())
            ).id
            == identifier
        )
        with pytest.raises(PolicyError, match="different payload"):
            create_probe(
                db,
                actor,
                app_id,
                binding_id,
                ProbeInput(scenario="terminal"),
                "submit",
                str(uuid4()),
            )
        with pytest.raises(PolicyError, match="unresolved work"):
            create_probe(
                db, actor, app_id, binding_id, ProbeInput(), "new", str(uuid4())
            )
    client, headers, engine, _ = registry
    client.post(
        f"/api/v1/operations/{identifier}/cancel",
        headers={**headers[2], "Idempotency-Key": "c"},
    )
    with Session(engine) as db:
        models = (
            Operation,
            OperationCommand,
            OperationReservation,
            QueueProbe,
            AuditEvent,
        )
        before = [
            db.scalar(select(func.count()).select_from(model)) for model in models
        ]

        def fail(*args: object, **kwargs: object) -> None:
            raise RuntimeError("secret-diagnostic")

        monkeypatch.setattr(audit_service, "record_audit", fail)
        with pytest.raises(RuntimeError):
            create_probe(
                db,
                db.get(User, 2),
                app_id,
                binding_id,
                ProbeInput(),
                "rollback",
                str(uuid4()),
            )
        assert [
            db.scalar(select(func.count()).select_from(model)) for model in models
        ] == before


@pytest.mark.parametrize(
    "scenario,states",
    [
        ("success", ["succeeded"]),
        ("terminal", ["failed"]),
        ("transient", ["retry_wait", "retry_wait", "succeeded"]),
        ("unknown", ["reconciling", "needs_attention"]),
    ],
)
def test_worker_dispatch_backoff_and_reservations(
    registry: tuple, scenario: str, states: list[str]
) -> None:
    from models.operations import Operation, OperationReservation, QueueProbe
    from worker import run_one

    identifier = queued(registry, scenario)
    engine = registry[2]
    for status in states:
        assert run_one(sessionmaker(engine), str(uuid4()))
        with Session(engine) as db:
            operation = db.get(Operation, identifier)
            assert operation.status == status
            assert operation.observed_at is not None
            reservation = db.get(OperationReservation, operation.binding_id)
            assert bool(reservation) == (status not in {"succeeded", "failed"})
            if status in {"succeeded", "failed"}:
                assert (
                    db.scalar(
                        select(QueueProbe.result).where(
                            QueueProbe.operation_id == identifier
                        )
                    )
                    == status
                )
            if status == "retry_wait":
                assert operation.available_at > operation.observed_at
        due(engine, identifier)


def test_expiry_fences_result_heartbeat_and_related_resource(registry: tuple) -> None:
    from models.operations import Operation, OperationAttempt, QueueProbe
    from services.queue_service import LostLease, claim, finish, heartbeat

    identifier = queued(registry)
    engine = registry[2]
    with Session(engine) as db:
        old = claim(db, str(uuid4()))
    with Session(engine) as db:
        assert claim(db, str(uuid4())) is None
    due(engine, identifier, expire=True)
    with Session(engine) as db:
        # Expired owner is fenced even before a replacement claims it.
        with pytest.raises(LostLease):
            finish(db, old, "succeeded")
        current = claim(db, str(uuid4()))
        assert current.phase == "reconcile" and current.token > old.token
        with pytest.raises(LostLease):
            heartbeat(db, old)
        with pytest.raises(LostLease):
            finish(db, old, "succeeded")
        assert db.get(Operation, identifier).status == "reconciling"
        assert db.scalar(select(QueueProbe.result)) is None
        assert (
            db.scalar(
                select(OperationAttempt.outcome).where(
                    OperationAttempt.fencing_token == old.token
                )
            )
            == "lease_expired"
        )


@pytest.mark.parametrize(
    "change", ["inactive", "role", "team", "archived", "binding", "disabled"]
)
def test_worker_rechecks_current_authorization(registry: tuple, change: str) -> None:
    from models.database import User
    from models.operations import Operation
    from models.platform import (
        Application,
        ApplicationRole,
        Environment,
        EnvironmentBinding,
        TeamMembership,
    )
    from worker import run_one

    identifier = queued(registry)
    engine = registry[2]
    with Session(engine) as db:
        operation = db.get(Operation, identifier)
        if change == "inactive":
            db.get(User, 2).is_active = False
        elif change in {"role", "team"}:
            db.execute(
                delete(ApplicationRole).where(ApplicationRole.role == "operator")
            )
            if change == "team":
                db.add(
                    ApplicationRole(
                        application_id=operation.application_id,
                        team_id=UUID(registry[3]),
                        role="operator",
                    )
                )
                db.execute(delete(TeamMembership).where(TeamMembership.user_id == 2))
        elif change == "archived":
            db.get(Application, operation.application_id).lifecycle = "archived"
        elif change == "binding":
            db.get(EnvironmentBinding, operation.binding_id).version += 1
        else:
            db.get(
                Environment,
                db.get(EnvironmentBinding, operation.binding_id).environment_id,
            ).enabled = False
        db.commit()
    assert run_one(sessionmaker(engine), str(uuid4()))
    with Session(engine) as db:
        assert db.get(Operation, identifier).status == "failed"
        assert db.get(Operation, identifier).diagnostic_code == "authorization_changed"


def test_running_cancel_is_intent_and_uncertain_reconciliation_retains_conflict(
    registry: tuple,
) -> None:
    from models.operations import OperationReservation
    from services.queue_service import claim, finish, heartbeat

    client, headers, engine, _ = registry
    identifier = queued(registry, "unknown")
    path = f"/api/v1/operations/{identifier}"
    keys = {**headers[2], "Idempotency-Key": "cancel"}
    with Session(engine) as db:
        item = claim(db, str(uuid4()))
    assert client.post(path + "/cancel", headers=keys).json()["status"] == "running"
    with Session(engine) as db:
        assert heartbeat(db, item)
        finish(db, item, "unknown")
        item = claim(db, str(uuid4()))
        finish(db, item, "unknown")
        assert db.scalar(select(func.count()).select_from(OperationReservation)) == 1
    assert client.post(path + "/retry", headers=keys).status_code == 409
    assert client.post(path + "/reconcile", headers=keys, json={}).status_code == 422
    response = client.post(
        path + "/reconcile", headers=keys, json={"evidence": "secret pasted reason"}
    )
    assert response.status_code == 202
    assert (
        client.post(
            path + "/reconcile", headers=keys, json={"evidence": "changed"}
        ).status_code
        == 409
    )
    assert (
        client.post(
            path + "/reconcile", headers=keys, json={"evidence": "secret pasted reason"}
        ).json()
        == response.json()
    )
    assert (
        "secret pasted" not in client.get(path + "/attempts", headers=headers[2]).text
    )


def test_readiness_telemetry_and_attempt_pagination(registry: tuple) -> None:
    from worker import run_one

    client, headers, engine, _ = registry
    identifier = queued(registry, "transient")
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503
    run_one(sessionmaker(engine), str(uuid4()))
    assert client.get("/ready").status_code == 200
    assert client.get("/api/v1/queue/telemetry", headers=headers[2]).status_code == 403
    telemetry = client.get("/api/v1/queue/telemetry", headers=headers[1]).json()
    assert telemetry["counts"] == {"retry_wait": 1}
    assert telemetry["live_workers"] == 1
    due(engine, identifier)
    run_one(sessionmaker(engine), str(uuid4()))
    path = f"/api/v1/operations/{identifier}/attempts"
    first = client.get(path + "?limit=1", headers=headers[2]).json()
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = client.get(
        path, params={"cursor": first["next_cursor"], "limit": 1}, headers=headers[2]
    ).json()
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert client.get(path + "?limit=101", headers=headers[2]).status_code == 422
    assert client.get(path + "?cursor=bad", headers=headers[2]).status_code == 422


def test_bounded_failure_and_sanitized_exception(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    import worker
    from models.operations import Operation, OperationReservation

    identifier = queued(registry)
    engine = registry[2]
    monkeypatch.setattr(worker, "probe", lambda *args: "transient")
    for _ in range(3):
        assert worker.run_one(sessionmaker(engine), str(uuid4()))
        due(engine, identifier)
    assert not worker.run_one(sessionmaker(engine), str(uuid4()))
    with Session(engine) as db:
        operation = db.get(Operation, identifier)
        assert operation.status == "failed"
        assert operation.diagnostic_code == "retry_exhausted"
        assert operation.attempt_count == 3
        assert db.get(OperationReservation, operation.binding_id) is None
    client, headers, _, _ = registry
    response = client.post(
        f"/api/v1/operations/{identifier}/retry",
        headers={**headers[2], "Idempotency-Key": "retry"},
    )
    retry_id = response.json()["operation_id"]

    def fail(*args: object) -> None:
        raise RuntimeError("password=never-expose-this")

    monkeypatch.setattr(worker, "probe", fail)
    assert worker.run_one(sessionmaker(engine), str(uuid4()))
    response = client.get(f"/api/v1/operations/{retry_id}", headers=headers[2])
    assert response.json()["status"] == "reconciling"
    assert "never-expose" not in response.text
    assert (
        "never-expose"
        not in client.get(
            f"/api/v1/operations/{retry_id}/attempts", headers=headers[2]
        ).text
    )


def test_ui_operation_cancel_retry_and_attempt_history(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_registry_ui import control, signed_in
    from worker import run_one

    identifier = queued(registry)
    app = signed_in(registry, monkeypatch, 2)
    assert any("Simulated execution" in caption.value for caption in app.caption)
    control(app.button, "Cancel").click().run()
    assert not app.exception
    assert any("cancelled" in message.value for message in app.success)
    control(app.button, "Retry").click().run()
    assert not app.exception
    assert run_one(sessionmaker(registry[2]), str(uuid4()))
    control(app.button, "Refresh operations").click().run()
    assert not app.exception
    assert any(
        "outcome" in frame.value.columns
        and "succeeded" in frame.value["outcome"].tolist()
        for frame in app.dataframe
    )
    client, headers, _, _ = registry
    assert (
        client.get(f"/api/v1/operations/{identifier}", headers=headers[2]).json()[
            "status"
        ]
        == "cancelled"
    )


def test_lease_expiring_during_result_flush_rolls_back(
    registry: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.operations import Operation, QueueProbe
    from services import audit_service, queue_service

    identifier = queued(registry)
    engine = registry[2]
    with Session(engine) as db:
        item = queue_service.claim(db, str(uuid4()))
    real_audit = audit_service.record_audit

    def slow_audit(*args: object, **kwargs: object) -> None:
        real_audit(*args, **kwargs)
        # Time elapses during a flushed statement while the row remains locked.
        monkeypatch.setattr(
            queue_service,
            "now",
            lambda db: queue_service.aware(deadline) + timedelta(seconds=1),
        )

    with Session(engine) as db:
        deadline = db.get(Operation, identifier).lease_expires_at
        db.rollback()
        monkeypatch.setattr(audit_service, "record_audit", slow_audit)
        with pytest.raises(queue_service.LostLease):
            queue_service.finish(db, item, "succeeded")
        assert db.get(Operation, identifier).status == "running"
        assert db.scalar(select(QueueProbe.result)) is None
