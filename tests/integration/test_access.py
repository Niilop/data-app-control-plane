"""PostgreSQL grant uniqueness, lifecycle serialization and migration preservation."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.orm import Session
from test_environment_bindings import setup_binding
from test_migrations import HEAD_REVISION, _alembic_config
from test_migrations import isolated_schema as isolated_schema
from test_migrations import registry_engine as registry_engine
from test_operations import prepare, submit

pytestmark = pytest.mark.integration


def test_concurrent_requests_and_decisions_create_one_grant(registry_engine) -> None:
    from models.access import AccessRequest
    from models.access_schemas import AccessDecision, AccessRequestInput
    from models.database import User
    from models.platform import ApplicationRole, AuditEvent
    from services.access_service import decide, request_access
    from services.policy_service import PolicyError

    app_id, _, _ = setup_binding(registry_engine)
    barrier = Barrier(2)

    def request():
        with Session(registry_engine) as db:
            actor = db.get(User, 3)
            barrier.wait(timeout=10)
            return request_access(
                db,
                actor,
                app_id,
                AccessRequestInput(requested_role="viewer", reason="Review"),
                str(uuid4()),
            ).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: request(), range(2)))
    assert ids[0] == ids[1]

    def approve():
        with Session(registry_engine) as db:
            actor = db.get(User, 2)
            barrier.wait(timeout=10)
            return decide(
                db,
                actor,
                ids[0],
                AccessDecision(decision="approved", reason="Yes"),
                str(uuid4()),
            ).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: approve(), range(2))) == ["approved", "approved"]
    with Session(registry_engine) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(AccessRequest)) == 1
        assert (
            db.scalar(
                sa.select(sa.func.count())
                .select_from(ApplicationRole)
                .where(ApplicationRole.user_id == 3)
            )
            == 1
        )
        assert (
            db.scalar(
                sa.select(sa.func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "access.approved")
            )
            == 1
        )
        with pytest.raises(PolicyError, match="already resolved"):
            decide(
                db,
                db.get(User, 2),
                ids[0],
                AccessDecision(decision="rejected", reason="No"),
                str(uuid4()),
            )


def test_archive_wins_against_waiting_submission(registry_engine) -> None:
    from models.access_schemas import ArchiveInput
    from models.database import User
    from models.operations import Operation
    from models.platform import Application
    from services.access_service import archive
    from services.policy_service import PolicyError

    app_id, binding_id = prepare(registry_engine)
    reached_lock = Event()

    def waiting(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement and "FROM applications" in statement:
            reached_lock.set()

    def send():
        try:
            return submit(registry_engine, app_id, binding_id)
        except PolicyError as exc:
            return exc.code

    with Session(registry_engine) as blocker:
        blocker.scalar(
            sa.select(Application).where(Application.id == app_id).with_for_update()
        )
        sa.event.listen(registry_engine, "before_cursor_execute", waiting)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(send)
                try:
                    assert reached_lock.wait(timeout=10)
                    archive(
                        blocker,
                        blocker.get(User, 2),
                        app_id,
                        ArchiveInput(expected_version=1),
                        str(uuid4()),
                    )
                finally:
                    blocker.rollback()
                assert future.result(timeout=10) == "application_archived"
        finally:
            sa.event.remove(registry_engine, "before_cursor_execute", waiting)
    with Session(registry_engine) as db:
        assert db.get(Application, app_id).lifecycle == "archived"
        assert db.scalar(sa.select(sa.func.count()).select_from(Operation)) == 0


def test_submission_wins_against_waiting_archive(registry_engine, monkeypatch) -> None:
    from models.access_schemas import ArchiveInput
    from models.database import User
    from models.operations import OperationReservation
    from models.platform import Application
    from services import operation_service
    from services.access_service import archive
    from services.policy_service import PolicyError

    app_id, binding_id = prepare(registry_engine)
    inserted, release, reached_archive = Event(), Event(), Event()
    original = operation_service.remember

    def pause(*args, **kwargs):
        original(*args, **kwargs)
        inserted.set()
        assert release.wait(timeout=10)

    monkeypatch.setattr(operation_service, "remember", pause)

    def waiting(conn, cursor, statement, parameters, context, executemany):
        if (
            inserted.is_set()
            and "FOR UPDATE" in statement
            and "FROM applications" in statement
        ):
            reached_archive.set()

    def retire():
        with Session(registry_engine) as db:
            try:
                archive(
                    db,
                    db.get(User, 2),
                    app_id,
                    ArchiveInput(expected_version=1),
                    str(uuid4()),
                )
            except PolicyError as exc:
                return exc.code
            return "unexpected_success"

    sa.event.listen(registry_engine, "before_cursor_execute", waiting)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            queued = pool.submit(submit, registry_engine, app_id, binding_id)
            try:
                assert inserted.wait(timeout=10)
                archived = pool.submit(retire)
                assert reached_archive.wait(timeout=10)
            finally:
                release.set()
            queued.result(timeout=10)
            assert archived.result(timeout=10) == "unresolved_work"
    finally:
        sa.event.remove(registry_engine, "before_cursor_execute", waiting)
    with Session(registry_engine) as db:
        assert db.get(Application, app_id).lifecycle == "registered"
        assert db.get(OperationReservation, binding_id) is not None


def test_decider_loses_ownership_while_waiting(registry_engine) -> None:
    from models.access_schemas import AccessDecision, AccessRequestInput
    from models.database import User
    from models.platform import Application, ApplicationRole
    from services.access_service import decide, request_access
    from services.policy_service import PolicyError

    app_id, _, _ = setup_binding(registry_engine)
    with Session(registry_engine) as db:
        identifier = request_access(
            db,
            db.get(User, 3),
            app_id,
            AccessRequestInput(requested_role="viewer", reason="Review"),
            str(uuid4()),
        ).id
    reached_lock = Event()

    def waiting(conn, cursor, statement, parameters, context, executemany):
        if "FOR UPDATE" in statement and "FROM applications" in statement:
            reached_lock.set()

    def send():
        with Session(registry_engine) as db:
            try:
                decide(
                    db,
                    db.get(User, 2),
                    identifier,
                    AccessDecision(decision="approved", reason="Yes"),
                    str(uuid4()),
                )
            except PolicyError as exc:
                return exc.code
            return "unexpected_success"

    with Session(registry_engine) as blocker:
        app = blocker.scalar(
            sa.select(Application).where(Application.id == app_id).with_for_update()
        )
        sa.event.listen(registry_engine, "before_cursor_execute", waiting)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(send)
                try:
                    assert reached_lock.wait(timeout=10)
                    app.owner_user_id = 1
                finally:
                    blocker.commit()
                assert future.result(timeout=10) == "forbidden"
        finally:
            sa.event.remove(registry_engine, "before_cursor_execute", waiting)
    with Session(registry_engine) as db:
        assert (
            db.scalar(sa.select(ApplicationRole).where(ApplicationRole.user_id == 3))
            is None
        )


def test_upgrade_preserves_t07_and_downgrade_refuses_request_history(
    registry_engine,
) -> None:
    from models.access import AccessRequest
    from models.access_schemas import AccessRequestInput
    from models.database import User
    from services.access_service import request_access
    from sqlalchemy.exc import IntegrityError

    app_id, binding_id = prepare(registry_engine)
    submit(registry_engine, app_id, binding_id)
    with registry_engine.connect() as conn:
        before = {
            table: conn.execute(sa.text(f"SELECT * FROM {table} ORDER BY id")).all()
            for table in (
                "applications",
                "application_roles",
                "operations",
                "audit_events",
            )
        }
    command.downgrade(_alembic_config(), "010_simulated_job_runs")
    command.upgrade(_alembic_config(), "head")
    with registry_engine.connect() as conn:
        for table, rows in before.items():
            assert (
                conn.execute(sa.text(f"SELECT * FROM {table} ORDER BY id")).all()
                == rows
            )
    with Session(registry_engine) as db:
        request_access(
            db,
            db.get(User, 3),
            app_id,
            AccessRequestInput(requested_role="viewer", reason="Review"),
            str(uuid4()),
        )
        db.add(
            AccessRequest(
                application_id=app_id,
                requested_by=3,
                requested_role="viewer",
                reason="Duplicate",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    with pytest.raises(RuntimeError, match="access request history"):
        command.downgrade(_alembic_config(), "010_simulated_job_runs")
    with registry_engine.connect() as conn:
        assert conn.scalar(sa.text("SELECT count(*) FROM access_requests")) == 1
        assert (
            conn.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == HEAD_REVISION
        )
