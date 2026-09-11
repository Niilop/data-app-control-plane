"""Real PostgreSQL migrations, constraints and environment-lock serialization."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.orm import Session
from test_migrations import _alembic_config, _scoped_database_url
from test_migrations import isolated_schema as isolated_schema
from test_migrations import registry_engine as registry_engine

pytestmark = pytest.mark.integration


def setup_binding(engine: sa.Engine, *, bind: bool = True) -> tuple:
    from models.database import User
    from models.environment_schemas import BindingCreate, EnvironmentCreate
    from models.platform import Team
    from models.platform_schemas import ApplicationCreate
    from services.application_service import create_application
    from services.environment_service import create_binding, create_environment

    with Session(engine) as db:
        admin, member = db.get(User, 1), db.get(User, 2)
        application = create_application(
            db,
            member,
            ApplicationCreate(
                slug="environment-app",
                name="Environment app",
                owning_team_id=db.scalar(sa.select(Team.id)),
                owner_user_id=2,
                data_owner_user_id=2,
                repository_url="https://github.com/example/environments",
            ),
            str(uuid4()),
        )
        application_id = application.id
        environment = create_environment(
            db,
            admin,
            EnvironmentCreate(
                name="simulated-sandbox",
                workspace_ref="simulated://sandbox",
                allowed_executor="simulated",
                allowed_bundle_targets=["sandbox"],
            ),
            str(uuid4()),
        )
        environment_id = environment.id
        binding_id = None
        if bind:
            binding = create_binding(
                db,
                admin,
                application_id,
                BindingCreate(environment_id=environment_id, bundle_target="sandbox"),
                str(uuid4()),
            )
            binding_id = binding.id
        return application_id, environment_id, binding_id


def test_upgrade_from_t02_preserves_application_and_audit(isolated_schema: str) -> None:
    from models.database import User
    from models.platform import Application, AuditEvent, Team

    config = _alembic_config()
    command.upgrade(config, "005_owned_applications")
    engine = sa.create_engine(_scoped_database_url(isolated_schema))
    try:
        with Session(engine) as db:
            user = User(
                email="preserve@example.test",
                username="preserve",
                password_hash="preserved",
            )
            team = Team(name="Preserved team")
            db.add_all([user, team])
            db.flush()
            application = Application(
                slug="preserve",
                name="Preserved app",
                owning_team_id=team.id,
                owner_user_id=user.id,
                data_owner_user_id=user.id,
                repository_url="https://github.com/example/preserve",
                bundle_root=".",
                created_by=user.id,
            )
            db.add(application)
            db.flush()
            audit = AuditEvent(
                actor_user_id=user.id,
                action="application.registered",
                target_type="application",
                target_id=str(application.id),
                application_id=application.id,
                request_id=str(uuid4()),
                details={"preserved": True},
            )
            db.add(audit)
            db.commit()
            application_id, audit_id = application.id, audit.id
        command.upgrade(config, "head")
        with Session(engine) as db:
            assert db.get(Application, application_id).name == "Preserved app"
            assert db.get(Application, application_id).version == 1
            assert db.get(AuditEvent, audit_id).details == {"preserved": True}
    finally:
        engine.dispose()


def test_binding_unique_fk_and_transaction_rollback(
    registry_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.database import User
    from models.environment_schemas import BindingCreate, EnvironmentUpdate
    from models.platform import AuditEvent, Environment, EnvironmentBinding
    from services import audit_service
    from services.environment_service import create_binding, update_environment
    from services.policy_service import PolicyError

    application_id, environment_id, binding_id = setup_binding(registry_engine)
    with Session(registry_engine) as db:
        admin = db.get(User, 1)
        before = db.scalar(sa.select(sa.func.count()).select_from(AuditEvent))
        with pytest.raises(PolicyError) as conflict:
            create_binding(
                db,
                admin,
                application_id,
                BindingCreate(environment_id=environment_id, bundle_target="sandbox"),
                str(uuid4()),
            )
        assert conflict.value.status == 409
        assert db.scalar(sa.select(sa.func.count()).select_from(AuditEvent)) == before
        for app_id, env_id in (
            (application_id, environment_id),
            (uuid4(), environment_id),
            (application_id, uuid4()),
        ):
            with pytest.raises(sa.exc.IntegrityError):
                db.add(
                    EnvironmentBinding(
                        application_id=app_id,
                        environment_id=env_id,
                        bundle_target="sandbox",
                        config={"schema_version": 1},
                    )
                )
                db.flush()
            db.rollback()
        original = audit_service.record_audit

        def fail_after_flush(*args: object, **kwargs: object) -> None:
            original(*args, **kwargs)
            raise RuntimeError("injected transaction failure")

        with monkeypatch.context() as patch:
            patch.setattr(audit_service, "record_audit", fail_after_flush)
            with pytest.raises(RuntimeError):
                update_environment(
                    db,
                    admin,
                    environment_id,
                    EnvironmentUpdate(expected_version=1, enabled=False),
                    str(uuid4()),
                )
        assert db.get(Environment, environment_id).enabled is True
        assert db.get(Environment, environment_id).version == 1
        assert db.get(EnvironmentBinding, binding_id).version == 1
        assert db.scalar(sa.select(sa.func.count()).select_from(AuditEvent)) == before


def test_concurrent_binding_updates_have_one_winner(registry_engine: sa.Engine) -> None:
    from models.database import User
    from models.environment_schemas import BindingUpdate
    from models.platform import AuditEvent, EnvironmentBinding
    from services.environment_service import update_binding
    from services.policy_service import PolicyError

    application_id, _, binding_id = setup_binding(registry_engine)
    barrier = Barrier(2)

    def change(rows: int) -> str:
        with Session(registry_engine) as db:
            actor = db.get(User, 1)
            assert db.get(EnvironmentBinding, binding_id).version == 1
            barrier.wait(timeout=10)
            try:
                update_binding(
                    db,
                    actor,
                    application_id,
                    binding_id,
                    BindingUpdate(
                        expected_version=1, config={"synthetic_row_count": rows}
                    ),
                    str(uuid4()),
                )
                return "updated"
            except PolicyError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, [200, 300]))
    assert sorted(results) == ["stale_version", "updated"]
    with Session(registry_engine) as db:
        assert db.get(EnvironmentBinding, binding_id).version == 2
        assert (
            db.scalar(
                sa.select(sa.func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "binding.updated")
            )
            == 1
        )


def test_environment_edit_serializes_with_binding_creation(
    registry_engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from models.database import User
    from models.environment_schemas import BindingCreate, EnvironmentUpdate
    from models.platform import Environment, EnvironmentBinding
    from services import audit_service
    from services.environment_service import create_binding, update_environment

    application_id, environment_id, _ = setup_binding(registry_engine, bind=False)
    created = Event()
    updating = Event()
    release = Event()
    original = audit_service.record_audit

    def pause_creation(*args: object, **kwargs: object) -> None:
        if args[3] == "binding.created":
            created.set()
            assert release.wait(timeout=10)
        original(*args, **kwargs)

    monkeypatch.setattr(audit_service, "record_audit", pause_creation)

    def bind() -> None:
        with Session(registry_engine) as db:
            create_binding(
                db,
                db.get(User, 1),
                application_id,
                BindingCreate(environment_id=environment_id, bundle_target="sandbox"),
                str(uuid4()),
            )

    def disable() -> None:
        with Session(registry_engine) as db:
            actor = db.get(User, 1)
            updating.set()
            update_environment(
                db,
                actor,
                environment_id,
                EnvironmentUpdate(expected_version=1, enabled=False),
                str(uuid4()),
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(bind)
        try:
            assert created.wait(timeout=10)
            second = pool.submit(disable)
            assert updating.wait(timeout=10)
        finally:
            release.set()
        first.result(timeout=10)
        second.result(timeout=10)
    with Session(registry_engine) as db:
        assert db.get(Environment, environment_id).enabled is False
        binding = db.scalar(sa.select(EnvironmentBinding))
        assert binding.version == 2  # The concurrent environment update included it.
