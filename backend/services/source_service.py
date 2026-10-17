"""Explicitly enabled GitHub reads with immutable commit pins and fenced publication."""

import os
from uuid import UUID, uuid4

from core.config import get_settings
from integrations.github import GitHub
from integrations.source_archive import capture_archive
from models.database import User
from models.operations import Operation
from models.platform import Application, EnvironmentBinding, utcnow
from models.source import CIRun, SourceCapture
from models.source_schemas import SourceInput
from services import delivery_service as delivery
from services.application_service import transaction
from services.operation_service import audit, remember, replay
from services.policy_service import (
    PolicyError,
    get_application,
    mutable_application,
    require_developer,
)
from services.queue_service import Claim, owned
from sqlalchemy.orm import Session, sessionmaker


def repository(app: Application) -> str:
    return app.repository_url.removeprefix("https://github.com/")


def enabled(app: Application) -> bool:
    settings = get_settings()
    return settings.github_reads_enabled and repository(app).lower() in {
        value.lower() for value in settings.github_allowed_repositories
    }


def require_enabled(app: Application) -> None:
    if not enabled(app):
        raise PolicyError(
            409,
            "github_reads_disabled",
            "GitHub reads require administrator configuration for this repository",
        )


def get_capture(db: Session, actor: User, identifier: UUID) -> SourceCapture:
    capture = db.get(SourceCapture, identifier)
    if capture is None:
        raise PolicyError(404, "not_found", "Source capture not found")
    get_application(db, actor, capture.application_id)
    return capture


def for_operation(db: Session, operation: Operation) -> SourceCapture:
    capture = db.get(SourceCapture, UUID(operation.payload["source_capture_id"]))
    if capture is None or capture.application_id != operation.application_id:
        raise PolicyError(409, "invalid_source", "Source capture unavailable")
    return capture


def authorize_operation(db: Session, actor: User, operation: Operation) -> None:
    binding = delivery.check_preparation(
        db,
        actor,
        operation.application_id,
        operation.binding_id,
        operation.binding_version,
    )
    app = get_application(db, actor, operation.application_id)
    require_enabled(app)
    capture = for_operation(db, operation)
    if (
        capture.repository_url != app.repository_url
        or capture.bundle_root != app.bundle_root
        or capture.binding_snapshot != delivery.snapshot(db, binding)
        or capture.template_digest != delivery.template(db).content_digest
        or (operation.kind == "capture_github" and capture.operation_id != operation.id)
        or (operation.kind == "refresh_github_ci" and capture.artifact_digest is None)
    ):
        raise PolicyError(
            409, "stale_source", "Repository or binding policy changed; capture again"
        )


def enqueue_capture(
    db: Session,
    actor: User,
    app: Application,
    binding: EnvironmentBinding,
    ref: str,
    request_id: str,
    previous: SourceCapture | None = None,
) -> Operation:
    require_enabled(app)
    approved = delivery.template(db)
    identifier = uuid4()
    operation = delivery.enqueue(
        db,
        actor,
        binding,
        "capture_github",
        {"schema_version": 1, "source_capture_id": str(identifier)},
        request_id,
        previous.operation_id if previous else None,
    )
    capture = SourceCapture(
        id=identifier,
        application_id=app.id,
        operation_id=operation.id,
        repository_url=app.repository_url,
        bundle_root=app.bundle_root,
        requested_ref=ref,
        binding_snapshot=delivery.snapshot(db, binding),
        template_id=approved.id,
        template_digest=approved.content_digest,
        commit_sha=previous.commit_sha if previous else None,
        repository_id=previous.repository_id if previous else None,
    )
    db.add(capture)
    db.flush()
    return operation


def capture(
    db: Session,
    actor: User,
    application_id: UUID,
    data: SourceInput,
    key: str,
    request_id: str,
) -> Operation:
    with transaction(db):
        require_developer(db, actor, get_application(db, actor, application_id))
        binding = db.get(EnvironmentBinding, data.binding_id)
        if binding is None or binding.application_id != application_id:
            raise PolicyError(422, "invalid_binding", "Binding is unavailable")
        delivery.lock_environment(db, binding.environment_id)
        app = mutable_application(db, actor, application_id)
        require_developer(db, actor, app)
        request = data.model_dump(mode="json")
        previous = replay(db, actor, "capture_github", application_id, key, request)
        if previous:
            return previous
        binding = delivery.check_preparation(
            db, actor, application_id, data.binding_id, data.expected_binding_version
        )
        operation = enqueue_capture(db, actor, app, binding, data.ref, request_id)
        remember(db, actor, "capture_github", application_id, key, request, operation)
        return operation


def refresh(
    db: Session, actor: User, capture_id: UUID, key: str, request_id: str
) -> Operation:
    with transaction(db):
        source = get_capture(db, actor, capture_id)
        binding = delivery.check_preparation(
            db,
            actor,
            source.application_id,
            UUID(source.binding_snapshot["binding_id"]),
            source.binding_snapshot["binding_version"],
        )
        payload = {"schema_version": 1, "source_capture_id": str(source.id)}
        previous = replay(db, actor, "refresh_github_ci", source.id, key, payload)
        if previous:
            return previous
        operation = delivery.enqueue(
            db, actor, binding, "refresh_github_ci", payload, request_id
        )
        authorize_operation(db, actor, operation)
        remember(db, actor, "refresh_github_ci", source.id, key, payload, operation)
        return operation


def retry_operation(
    db: Session, actor: User, operation: Operation, request_id: str
) -> Operation:
    authorize_operation(db, actor, operation)
    binding = db.get(EnvironmentBinding, operation.binding_id)
    assert binding is not None
    if operation.kind == "capture_github":
        source = for_operation(db, operation)
        return enqueue_capture(
            db,
            actor,
            get_application(db, actor, operation.application_id),
            binding,
            source.requested_ref,
            request_id,
            source,
        )
    return delivery.enqueue(
        db, actor, binding, operation.kind, operation.payload, request_id, operation.id
    )


def execute(sessions: sessionmaker[Session], item: Claim) -> dict:
    with sessions() as db, db.begin():
        operation = owned(db, item)
        source = for_operation(db, operation)
        db.expunge(source)
    adapter = GitHub(
        source.repository_url.removeprefix("https://github.com/"),
        os.environ.get("GITHUB_READ_TOKEN"),
    )
    if item.kind == "refresh_github_ci":
        assert source.repository_id is not None and source.commit_sha is not None
        adapter.verify_repository(source.repository_id)
        return {"runs": adapter.runs(source.repository_id, source.commit_sha)}
    if source.commit_sha is None:
        repo_id, commit = adapter.resolve(source.requested_ref)
        with sessions() as db, db.begin():
            operation = owned(db, item)
            actor = db.get(User, operation.requested_by)
            assert actor is not None
            authorize_operation(db, actor, operation)
            if operation.cancel_requested:
                return {"cancelled": True}
            persisted = for_operation(db, operation)
            persisted.repository_id, persisted.commit_sha = repo_id, commit
            audit(
                db,
                actor,
                operation,
                operation.request_id,
                "source.resolved",
                {"source_capture_id": str(persisted.id), "commit_sha": commit},
            )
            owned(
                db, item
            )  # A lock wait must not permit an expired lease to pin source.
        source.repository_id, source.commit_sha = repo_id, commit
    assert source.repository_id is not None
    adapter.verify_repository(source.repository_id)
    data = capture_archive(
        adapter.archive(source.commit_sha), source.bundle_root, source.binding_snapshot
    )
    return {"digest": delivery.store().put(data), "size": len(data)}


def record_result(db: Session, operation: Operation, result: dict) -> None:
    source = for_operation(db, operation)
    if operation.kind == "capture_github":
        delivery.record_artifact(
            db, result["digest"], result["size"], "application/zip"
        )
        source.artifact_digest = result["digest"]
        source.captured_at = utcnow()
        app = db.get(Application, source.application_id)
        assert app is not None
        app.repository_verified_at = source.captured_at
    else:
        for row in result["runs"]:
            db.add(
                CIRun(
                    application_id=source.application_id,
                    source_capture_id=source.id,
                    operation_id=operation.id,
                    commit_sha=source.commit_sha,
                    observed_at=utcnow(),
                    **row,
                )
            )
    actor = db.get(User, operation.requested_by)
    assert actor is not None
    audit(
        db,
        actor,
        operation,
        operation.request_id,
        "source.captured" if operation.kind == "capture_github" else "ci.observed",
        {
            "source_capture_id": str(source.id),
            "commit_sha": source.commit_sha,
            "run_count": len(result.get("runs", [])),
        },
    )
