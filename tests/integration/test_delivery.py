"""PostgreSQL preparation migration, immutable records and concurrent commands."""

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


def prepare(engine: sa.Engine) -> tuple:
    from models.database import User
    from models.delivery_schemas import GenerationInput
    from services.delivery_service import generate

    app, _, binding = setup_binding(engine)
    with Session(engine) as db:
        operation = generate(
            db,
            db.get(User, 2),
            app,
            GenerationInput(binding_id=binding, expected_binding_version=1),
            "gen",
            str(uuid4()),
        )
        return app, binding, operation.id


def test_generation_replay_concurrency_and_db_immutability(
    registry_engine: sa.Engine, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.config import get_settings
    from models.database import User
    from models.delivery import DeploymentRevision, Generation, TemplateVersion
    from models.delivery_schemas import GenerationInput, RevisionInput
    from models.operations import Operation
    from services.delivery_service import create_revision, generate
    from services.template_service import template_digest
    from worker import run_one

    monkeypatch.setattr(get_settings(), "artifact_dir", str(tmp_path))
    app, _, binding = setup_binding(registry_engine)
    barrier = Barrier(2)

    def submit() -> object:
        with Session(registry_engine) as db:
            actor = db.get(User, 2)
            barrier.wait(timeout=10)
            return generate(
                db,
                actor,
                app,
                GenerationInput(binding_id=binding, expected_binding_version=1),
                "same",
                str(uuid4()),
            ).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert results[0] == results[1]
    assert run_one(sessionmaker(registry_engine), str(uuid4()))
    with Session(registry_engine) as db:
        assert (
            db.get(TemplateVersion, "python-batch:1.0.0").content_digest
            == template_digest()
        )
        assert db.get(Operation, results[0]).status == "succeeded"
        generation = db.scalar(sa.select(Generation))
        row = create_revision(
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
        identifier = row.id
    for statement in (
        "UPDATE deployment_revisions SET config_digest = 'bad'",
        "DELETE FROM deployment_revisions",
        "UPDATE artifacts SET size = 0",
        "UPDATE template_versions SET content_digest = 'bad'",
    ):
        with registry_engine.connect() as connection:
            with pytest.raises(sa.exc.DBAPIError, match="immutable"):
                connection.execute(sa.text(statement))
            connection.rollback()
    with Session(registry_engine) as db:
        assert db.get(DeploymentRevision, identifier).config_digest != "bad"


def test_two_binding_completions_share_one_artifact(
    registry_engine: sa.Engine, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.config import get_settings
    from models.database import User
    from models.delivery import Artifact, Generation
    from models.delivery_schemas import GenerationInput
    from models.environment_schemas import BindingCreate, EnvironmentCreate
    from services.delivery_service import generate
    from services.environment_service import create_binding, create_environment
    from worker import run_one

    monkeypatch.setattr(get_settings(), "artifact_dir", str(tmp_path))
    app, binding, _ = prepare(registry_engine)
    from models.platform import EnvironmentBinding

    with Session(registry_engine) as db:
        original = db.get(EnvironmentBinding, binding)
        target, config = original.bundle_target, original.config
        admin = db.get(User, 1)
        environment = create_environment(
            db,
            admin,
            EnvironmentCreate(
                name="Second preparation",
                workspace_ref="simulated://second",
                allowed_executor="simulated",
                allowed_bundle_targets=[target],
            ),
            str(uuid4()),
        )
        second = create_binding(
            db,
            admin,
            app,
            BindingCreate(
                environment_id=environment.id, bundle_target=target, config=config
            ),
            str(uuid4()),
        )
        generate(
            db,
            db.get(User, 2),
            app,
            GenerationInput(binding_id=second.id, expected_binding_version=1),
            "second",
            str(uuid4()),
        )
    barrier = Barrier(2)

    def work() -> bool:
        barrier.wait(timeout=10)
        return run_one(sessionmaker(registry_engine), str(uuid4()))

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(lambda _: work(), range(2)))
    with Session(registry_engine) as db:
        rows = list(db.scalars(sa.select(Generation)))
        assert (
            len(rows) == 2
            and rows[0].artifact_digest
            and rows[0].artifact_digest == rows[1].artifact_digest
        )
        assert db.scalar(sa.select(sa.func.count()).select_from(Artifact)) == 1
