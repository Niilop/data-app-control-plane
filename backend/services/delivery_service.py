"""Preparation commands share policy, durable queue and fenced completion."""

import ast
import json
import tomllib
from pathlib import Path
from uuid import UUID, uuid4

from core.config import get_settings
from integrations.artifact_store import ArtifactError, LocalArtifacts
from models.database import User
from models.delivery import (
    Artifact,
    DeploymentRevision,
    Generation,
    TemplateVersion,
    ValidationResult,
)
from models.delivery_schemas import GenerationInput, RevisionInput, TemplateParameters
from models.operations import Operation, OperationReservation
from models.platform import Application, EnvironmentBinding, utcnow
from services.application_service import transaction
from services.audit_service import record_audit
from services.environment_service import (
    lock_environment,
    require_local_simulation,
    require_target,
)
from services.operation_service import audit, remember, replay
from services.policy_service import (
    PolicyError,
    get_application,
    require_developer,
    visible_applications,
)
from services.template_service import (
    TEMPLATE_ID,
    canonical,
    render,
    sha,
    template_digest,
    unpack,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def store() -> LocalArtifacts:
    return LocalArtifacts(Path(get_settings().artifact_dir))


def template(db: Session) -> TemplateVersion:
    row = db.get(TemplateVersion, TEMPLATE_ID)
    if row is None or not row.active or row.content_digest != template_digest():
        raise PolicyError(
            409, "template_unavailable", "Approved template is unavailable"
        )
    return row


def check_preparation(
    db: Session, actor: User, application_id: UUID, binding_id: UUID, version: int
) -> EnvironmentBinding:
    require_local_simulation(get_settings())
    app = get_application(db, actor, application_id)
    require_developer(db, actor, app)
    if app.lifecycle == "archived":
        raise PolicyError(409, "archived", "Application is archived")
    binding = db.get(EnvironmentBinding, binding_id)
    if binding is None or binding.application_id != application_id:
        raise PolicyError(422, "invalid_binding", "Binding is unavailable")
    environment = lock_environment(db, binding.environment_id)
    db.refresh(binding)
    require_target(environment, binding.bundle_target)
    if binding.version != version:
        raise PolicyError(409, "stale_version", "Binding policy has changed")
    return binding


def snapshot(db: Session, binding: EnvironmentBinding) -> dict:
    environment = lock_environment(db, binding.environment_id)
    return {
        "binding_id": str(binding.id),
        "binding_version": binding.version,
        "environment_id": str(environment.id),
        "environment_version": environment.version,
        "workspace_ref": environment.workspace_ref,
        "bundle_target": binding.bundle_target,
        "execution_mode": "simulated",
        "allow_self_approval": environment.allow_self_approval,
        "config": binding.config,
    }


def enqueue(
    db: Session,
    actor: User,
    binding: EnvironmentBinding,
    kind: str,
    payload: dict,
    request_id: str,
    retry_of: UUID | None = None,
) -> Operation:
    reservation = db.get(OperationReservation, binding.id)
    if reservation:
        raise PolicyError(
            409,
            "operation_conflict",
            f"Binding has unresolved work: operation {reservation.operation_id}",
        )
    operation = Operation(
        id=uuid4(),
        application_id=binding.application_id,
        binding_id=binding.id,
        binding_version=binding.version,
        kind=kind,
        execution_mode="offline",
        requested_by=actor.id,
        request_id=request_id,
        payload=payload,
        retry_of=retry_of,
    )
    db.add(operation)
    db.flush()
    db.add(OperationReservation(binding_id=binding.id, operation_id=operation.id))
    if kind == "generate_bundle":
        db.add(
            Generation(
                operation_id=operation.id,
                application_id=binding.application_id,
                template_id=TEMPLATE_ID,
                parameters=payload["parameters"],
                binding_snapshot=payload["binding_snapshot"],
            )
        )
    audit(db, actor, operation, request_id, "operation.queued")
    db.flush()
    return operation


def generate(
    db: Session,
    actor: User,
    application_id: UUID,
    data: GenerationInput,
    key: str,
    request_id: str,
) -> Operation:
    with transaction(db):
        require_developer(db, actor, get_application(db, actor, application_id))
        # Serialize on environment just like binding administration; replay precedes stale checks.
        binding = db.get(EnvironmentBinding, data.binding_id)
        if binding is None or binding.application_id != application_id:
            raise PolicyError(422, "invalid_binding", "Binding is unavailable")
        lock_environment(db, binding.environment_id)
        request = data.model_dump(mode="json")
        previous = replay(db, actor, "generate_bundle", application_id, key, request)
        if previous:
            return previous
        binding = check_preparation(
            db, actor, application_id, data.binding_id, data.expected_binding_version
        )
        approved = template(db)
        app = get_application(db, actor, application_id)
        payload = {
            "schema_version": 1,
            "slug": app.slug,
            "parameters": data.parameters.model_dump(),
            "template_digest": approved.content_digest,
            "binding_snapshot": snapshot(db, binding),
        }
        # Pure preflight validation; archive creation remains worker-owned.
        operation = enqueue(db, actor, binding, "generate_bundle", payload, request_id)
        remember(db, actor, "generate_bundle", application_id, key, request, operation)
        return operation


def get_revision(db: Session, actor: User, identifier: UUID) -> DeploymentRevision:
    row = db.get(DeploymentRevision, identifier)
    if row is None:
        raise PolicyError(404, "not_found", "Revision not found")
    get_application(db, actor, row.application_id)
    return row


def create_revision(
    db: Session, actor: User, application_id: UUID, data: RevisionInput, request_id: str
) -> DeploymentRevision:
    with transaction(db):
        binding = check_preparation(
            db, actor, application_id, data.binding_id, data.expected_binding_version
        )
        generation = db.get(Generation, data.generation_id)
        if (
            generation is None
            or generation.application_id != application_id
            or generation.artifact_digest is None
        ):
            raise PolicyError(
                422, "invalid_generation", "Completed generation required"
            )
        captured = snapshot(db, binding)
        if generation.binding_snapshot != captured:
            raise PolicyError(
                409,
                "stale_generation",
                "Generate again for the current binding configuration",
            )
        approved = template(db)
        try:
            store().read(generation.artifact_digest)
        except ArtifactError:
            raise PolicyError(
                409, "artifact_unavailable", "Artifact integrity check failed"
            ) from None
        revision = DeploymentRevision(
            id=uuid4(),
            application_id=application_id,
            generation_id=generation.id,
            artifact_digest=generation.artifact_digest,
            template_id=approved.id,
            template_digest=approved.content_digest,
            binding_id=binding.id,
            binding_snapshot=captured,
            config_snapshot=captured["config"],
            config_digest=sha(canonical(captured["config"])),
            requested_by=actor.id,
        )
        db.add(revision)
        db.flush()
        record_audit(
            db,
            actor,
            request_id,
            "revision.created",
            "revision",
            revision.id,
            {
                "artifact_digest": revision.artifact_digest,
                "config_digest": revision.config_digest,
            },
            application_id,
        )
        return revision


def validate(
    db: Session, actor: User, revision_id: UUID, key: str, request_id: str
) -> Operation:
    with transaction(db):
        revision = get_revision(db, actor, revision_id)
        require_developer(
            db, actor, get_application(db, actor, revision.application_id)
        )
        binding = db.get(EnvironmentBinding, revision.binding_id)
        assert binding is not None
        lock_environment(db, binding.environment_id)
        payload = {
            "schema_version": 1,
            "revision_id": str(revision.id),
            "scope": "offline",
        }
        previous = replay(db, actor, "validate_offline", revision.id, key, payload)
        if previous:
            return previous
        binding = check_preparation(
            db,
            actor,
            revision.application_id,
            revision.binding_id,
            revision.binding_snapshot["binding_version"],
        )
        template(db)
        operation = enqueue(db, actor, binding, "validate_offline", payload, request_id)
        remember(db, actor, "validate_offline", revision.id, key, payload, operation)
        return operation


def authorize_operation(db: Session, actor: User, operation: Operation) -> None:
    check_preparation(
        db,
        actor,
        operation.application_id,
        operation.binding_id,
        operation.binding_version,
    )
    approved = template(db)
    if operation.kind == "generate_bundle":
        if operation.payload["template_digest"] != approved.content_digest:
            raise PolicyError(409, "template_unavailable", "Template content changed")
    else:
        revision = get_revision(db, actor, UUID(operation.payload["revision_id"]))
        if (
            revision.application_id != operation.application_id
            or revision.template_digest != approved.content_digest
        ):
            raise PolicyError(409, "invalid_revision", "Revision provenance mismatch")


def retry_operation(
    db: Session, actor: User, operation: Operation, request_id: str
) -> Operation:
    authorize_operation(db, actor, operation)
    binding = db.get(EnvironmentBinding, operation.binding_id)
    assert binding is not None
    return enqueue(
        db, actor, binding, operation.kind, operation.payload, request_id, operation.id
    )


def execute(db: Session, operation_id: UUID) -> tuple[bytes, str, str]:
    """Read immutable inputs, then do bounded static work. Never execute generated code."""
    operation = db.get(Operation, operation_id)
    assert operation is not None
    payload = operation.payload
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported preparation payload version")
    if operation.kind == "generate_bundle":
        binding = payload["binding_snapshot"]
        db.rollback()  # End the worker read transaction before rendering.
        return (
            render(
                payload["slug"],
                binding["bundle_target"],
                binding["config"],
                TemplateParameters.model_validate(payload["parameters"]),
            ),
            "application/zip",
            "passed",
        )
    revision = db.get(DeploymentRevision, UUID(payload["revision_id"]))
    assert revision is not None
    generation = db.get(Generation, revision.generation_id)
    assert generation is not None
    original = db.get(Operation, generation.operation_id)
    assert original is not None
    # These fully loaded immutable inputs remain readable after ending the read
    # transaction; filesystem/static work holds no DB transaction or locks.
    db.expunge_all()
    db.rollback()
    result, code = "passed", "approved_content_and_static_syntax"
    try:
        data = store().read(revision.artifact_digest)
        files = unpack(data)
        expected = render(
            original.payload["slug"],
            revision.binding_snapshot["bundle_target"],
            revision.config_snapshot,
            TemplateParameters.model_validate(generation.parameters),
        )
        if data != expected:
            raise ValueError("Unapproved content")
        for path, content in files.items():
            if path.endswith(".py"):
                ast.parse(content)
            elif path.endswith(".toml") or path == "uv.lock":
                tomllib.loads(content.decode())
        json.loads(files["manifest.json"])
    except (ArtifactError, ValueError, SyntaxError):
        result, code = "failed", "artifact_or_static_check_failed"
    report = canonical(
        {
            "schema_version": 1,
            "scope": "offline",
            "validator_version": "static-v1",
            "revision_id": str(revision.id),
            "artifact_digest": revision.artifact_digest,
            "config_digest": revision.config_digest,
            "result": result,
            "check": code,
            "workspace_validated": False,
            "code_executed": False,
        }
    )
    return report, "application/json", result


def record_result(
    db: Session, operation: Operation, result: tuple[str, int, str, str]
) -> None:
    digest, size, media_type, verdict = result
    # Unique digest publication must survive simultaneous completions across bindings.
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    db.execute(
        insert(Artifact)
        .values(digest=digest, size=size, media_type=media_type)
        .on_conflict_do_nothing(index_elements=["digest"])
    )
    artifact = db.get(Artifact, digest)
    if artifact is None or artifact.size != size or artifact.media_type != media_type:
        raise ValueError("Artifact metadata mismatch")
    if operation.kind == "generate_bundle":
        generation = db.scalar(
            select(Generation).where(Generation.operation_id == operation.id)
        )
        assert generation is not None
        generation.artifact_digest = digest
    else:
        db.add(
            ValidationResult(
                revision_id=UUID(operation.payload["revision_id"]),
                operation_id=operation.id,
                result=verdict,
                report_digest=digest,
                observed_at=utcnow(),
            )
        )


def download(db: Session, actor: User, digest: str) -> tuple[bytes, str]:
    applications = visible_applications(actor).with_only_columns(Application.id)
    generation = db.scalar(
        select(Generation.id)
        .where(
            Generation.artifact_digest == digest,
            Generation.application_id.in_(applications),
        )
        .limit(1)
    )
    report = db.scalar(
        select(ValidationResult.id)
        .join(DeploymentRevision, DeploymentRevision.id == ValidationResult.revision_id)
        .where(
            ValidationResult.report_digest == digest,
            DeploymentRevision.application_id.in_(applications),
        )
        .limit(1)
    )
    artifact = db.get(Artifact, digest) if generation or report else None
    if artifact is None:
        raise PolicyError(404, "not_found", "Artifact not found")
    try:
        return store().read(digest), artifact.media_type
    except ArtifactError:
        raise PolicyError(
            409, "artifact_unavailable", "Artifact integrity check failed"
        ) from None
