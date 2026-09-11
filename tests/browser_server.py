"""Disposable real API for Playwright; never connects to the developer database.

Run via the Playwright webServer configuration. Fixtures use ordinary API/services;
only setup bypasses HTTP to create local accounts and simulated operation states.
No fixture/reset endpoints are added to the application.
"""

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

os.environ.update(
    DATABASE_URL="postgresql://browser:browser@127.0.0.1:1/unused",
    SECRET_KEY="disposable-browser-test-signing-key",
    DEBUG="false",
    RUNTIME_PROFILE="local",
    DEPLOYMENT_EXECUTOR="simulated",
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import uvicorn  # noqa: E402
from core.config import get_settings  # noqa: E402
from core.database import Base, get_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import create_app  # noqa: E402
from models.database import User  # noqa: E402
from models.operation_schemas import ProbeInput  # noqa: E402
from services.auth_service import create_access_token, hash_password  # noqa: E402
from services.operation_service import create_probe  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from worker import run_one  # noqa: E402


def seed_delivery(engine: object, application_id: UUID, binding_id: UUID) -> None:
    """Generate, capture and validate once, so browser tests see finished records."""
    from models.delivery import Artifact
    from models.delivery_schemas import GenerationInput, RevisionCreate
    from services.delivery_service import (
        create_generation,
        create_revision,
        create_validation,
    )
    from sqlalchemy import select

    sessions = sessionmaker(engine)  # type: ignore[arg-type]
    with Session(engine) as db:  # type: ignore[arg-type]
        create_generation(
            db,
            db.get(User, 2),
            application_id,
            GenerationInput(
                template_name="python-batch",
                template_version="1.0.0",
                binding_id=binding_id,
                package_name="customer_analytics",
            ),
            "browser-generation",
            str(uuid4()),
        )
    assert run_one(sessions, str(uuid4()))
    with Session(engine) as db:  # type: ignore[arg-type]
        digest = db.scalar(select(Artifact.digest))
        assert digest, "Generation did not produce an artifact"
        revision = create_revision(
            db,
            db.get(User, 2),
            application_id,
            RevisionCreate(artifact_digest=digest, binding_id=binding_id),
            str(uuid4()),
        )
        create_validation(
            db, db.get(User, 2), revision.id, "browser-validation", str(uuid4())
        )
    assert run_one(sessions, str(uuid4()))


def run() -> None:
    with TemporaryDirectory(prefix="control-plane-browser-") as directory:
        # Disposable artifact store; never the developer's configured directory.
        os.environ["ARTIFACT_DIR"] = str(Path(directory) / "artifacts")
        get_settings.cache_clear()
        engine = create_engine(
            f"sqlite:///{directory}/browser.db",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def foreign_keys(connection: object, _: object) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        tables = [
            table
            for name, table in Base.metadata.tables.items()
            if name
            in {
                "users",
                "data_catalogs",
                "pipelines",
                "teams",
                "team_memberships",
                "applications",
                "application_roles",
                "audit_events",
                "environments",
                "environment_bindings",
                "operations",
                "operation_attempts",
                "operation_reservations",
                "queue_probes",
                "operation_commands",
                "worker_heartbeats",
                "template_versions",
                "artifacts",
                "deployment_revisions",
                "validation_results",
            }
        ]
        Base.metadata.create_all(engine, tables=tables)
        with Session(engine) as db:
            password = hash_password("Browser-test-password1!")
            for identifier, name in enumerate(
                ("admin", "developer", "viewer", "outsider"), 1
            ):
                db.add(
                    User(
                        id=identifier,
                        username=name,
                        email=f"{name}@example.test",
                        password_hash=password,
                        is_active=True,
                        is_platform_admin=identifier == 1,
                    )
                )
            db.commit()

        def session() -> Iterator[Session]:
            with Session(engine) as db:
                yield db

        app = create_app()
        app.dependency_overrides[get_db] = session
        headers = {
            "Authorization": "Bearer "
            + create_access_token({"sub": "admin@example.test"})
        }
        with TestClient(app) as client:

            def post(path: str, body: dict) -> dict:
                response = client.post("/api/v1" + path, headers=headers, json=body)
                assert response.is_success, response.text
                return response.json()

            team = post("/teams", {"name": "Engineering"})
            for user_id in (1, 2):
                post(f"/teams/{team['id']}/members", {"user_id": user_id})
            application = post(
                "/applications",
                {
                    "slug": "customer-analytics",
                    "name": "Customer analytics",
                    "description": "A shared view of customer activity and trusted reporting.",
                    "repository_url": "https://github.com/example/customer-analytics",
                    "owning_team_id": team["id"],
                    "owner_user_id": 1,
                    "data_owner_user_id": 2,
                },
            )
            for user_id, role in ((1, "operator"), (2, "developer"), (3, "viewer")):
                post(
                    f"/applications/{application['id']}/roles",
                    {"user_id": user_id, "role": role},
                )
            bindings = {}
            for target, scenario in (
                ("dev", "success"),
                ("test", "terminal"),
                ("qa", "unknown"),
            ):
                environment = post(
                    "/environments",
                    {
                        "name": f"Local sandbox {target}",
                        "workspace_ref": f"simulated://browser-{target}",
                        "allowed_executor": "simulated",
                        "allowed_bundle_targets": [target],
                        "enabled": True,
                        "allow_self_approval": False,
                    },
                )
                binding = post(
                    f"/applications/{application['id']}/bindings",
                    {
                        "environment_id": environment["id"],
                        "bundle_target": target,
                        "config": {
                            "schema_version": 1,
                            "synthetic_row_count": 100,
                            "max_runtime_seconds": 60,
                        },
                    },
                )
                bindings[target] = UUID(binding["id"])
                with Session(engine) as db:
                    create_probe(
                        db,
                        db.get(User, 1),
                        UUID(application["id"]),
                        UUID(binding["id"]),
                        ProbeInput(scenario=scenario),
                        target,
                        str(uuid4()),
                    )
                    if scenario != "success":
                        # Pick this operation, leaving the first probe queued for cancellation.
                        from datetime import timedelta

                        from models.operations import Operation
                        from models.platform import utcnow
                        from sqlalchemy import update

                        db.execute(
                            update(Operation)
                            .where(
                                Operation.status == "queued",
                                Operation.binding_id != UUID(binding["id"]),
                            )
                            .values(available_at=utcnow() + timedelta(days=1))
                        )
                        db.commit()
                if scenario != "success":
                    assert run_one(sessionmaker(engine), str(uuid4()))
                    if scenario == "unknown":
                        assert run_one(sessionmaker(engine), str(uuid4()))
            # Delivery state. Every remaining probe is deferred by the loop above,
            # so these are the only operations the worker cycles below can claim.
            seed_delivery(engine, UUID(application["id"]), bindings["dev"])
        uvicorn.run(
            app,
            host=os.environ.get("BROWSER_TEST_HOST", "127.0.0.1"),
            port=int(os.environ.get("BROWSER_TEST_PORT", "8001")),
            log_level="warning",
        )
        engine.dispose()


if __name__ == "__main__":
    run()
