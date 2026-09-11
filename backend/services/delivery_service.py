"""Generation, artifact capture, immutable revisions and offline validation.

Generation and validation are real local work, not a stand-in for a provider, so
their operations carry `execution_mode="local"`. Deployment execution remains
simulated and is not implemented here. Revisions are written once and never
updated: changing the artifact, binding, target or configuration creates a new
revision, which is what a later approval binds itself to.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from integrations import artifact_store
from models.database import User
from models.delivery import (
    Artifact,
    DeploymentRevision,
    TemplateVersion,
    ValidationResult,
)
from models.delivery_schemas import GenerationInput, RevisionCreate
from models.environment_schemas import SafeBindingConfig
from models.operations import Operation
from models.platform import Application, Environment, EnvironmentBinding
from services import audit_service
from services.application_service import transaction
from services.offline_validation import summarise, validate_offline
from services.operation_service import check_delivery, enqueue, remember, replay
from services.policy_service import PolicyError, get_application
from services.queue_service import Apply, Outcome
from services.template_service import (
    ARCHIVE_MEDIA_TYPE,
    REPORT_MEDIA_TYPE,
    GenerationError,
    Template,
    build_archive,
    canonical_digest,
    canonical_json,
    get_template,
    load_catalogue,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

# Bumped when the fields bound into an approval scope change; recorded per revision.
POLICY_VERSION = 1
# What a queue handler returns: the outcome, a safe diagnostic and the result
# writes to apply inside the fenced result transaction.
Handled = tuple[Outcome, str | None, Apply | None]


def now() -> datetime:
    return datetime.now(timezone.utc)


def sync_template(db: Session, template: Template) -> TemplateVersion:
    """Register a reviewed template version, or refuse if its content changed."""
    row = db.scalar(
        select(TemplateVersion).where(
            TemplateVersion.name == template.name,
            TemplateVersion.version == template.version,
        )
    )
    if row is None:
        row = TemplateVersion(
            id=uuid4(),
            name=template.name,
            version=template.version,
            content_digest=template.content_digest,
            parameter_schema={
                "payload_version": template.payload_version,
                "supplied": template.supplied_parameters,
                "derived": template.derived_parameters,
            },
            tool_versions=template.tool_versions,
            active=template.active,
        )
        db.add(row)
        db.flush()
        return row
    if row.content_digest != template.content_digest:
        # A published version is immutable: publish a new version instead.
        raise PolicyError(
            409,
            "template_digest_mismatch",
            "Template content no longer matches its registered digest",
        )
    return row


def template_values(
    template: Template,
    application: Application,
    binding: EnvironmentBinding,
    data: GenerationInput,
) -> dict[str, str]:
    """Every placeholder value; only two of them come from the request."""
    config = SafeBindingConfig.model_validate(binding.config)
    return {
        "application_slug": application.slug,
        "package_name": data.package_name,
        "package_dist_name": data.package_name.replace("_", "-"),
        "bundle_target": binding.bundle_target,
        "synthetic_output_path": data.synthetic_output_path,
        "synthetic_row_count": str(config.synthetic_row_count),
        "max_runtime_seconds": str(config.max_runtime_seconds),
        "template_name": template.name,
        "template_version": template.version,
    }


def create_generation(
    db: Session,
    actor: User,
    application_id: UUID,
    data: GenerationInput,
    key: str,
    request_id: str,
) -> Operation:
    """Queue deterministic local generation; the handler does the work, not the API."""
    with transaction(db):
        payload = data.model_dump(mode="json")
        previous = replay(db, actor, "bundle_generation", application_id, key, payload)
        if previous:
            return previous
        application, binding, _ = check_delivery(
            db, actor, application_id, data.binding_id
        )
        try:
            template = get_template(data.template_name, data.template_version)
        except GenerationError as error:
            raise PolicyError(422, error.code, str(error)) from None
        sync_template(db, template)
        operation = enqueue(
            db,
            actor,
            binding,
            payload,
            request_id,
            kind="bundle_generation",
            execution_mode="local",
            reserve=False,
        )
        remember(
            db, actor, "bundle_generation", application_id, key, payload, operation
        )
        return operation


def revision_scope(
    artifact: Artifact,
    template: TemplateVersion,
    binding: EnvironmentBinding,
    environment: Environment,
    config: dict,
) -> dict:
    """The exact identity a later approval binds to. No credentials, no free text."""
    return {
        "source_kind": "generated_artifact",
        "artifact_digest": artifact.digest,
        "template": {
            "name": template.name,
            "version": template.version,
            "content_digest": template.content_digest,
        },
        "binding": {
            "id": str(binding.id),
            "version": binding.version,
            "bundle_target": binding.bundle_target,
        },
        "environment": {
            "id": str(environment.id),
            "version": environment.version,
            "workspace_ref": environment.workspace_ref,
            "enabled": environment.enabled,
            "allowed_executor": environment.allowed_executor,
            "allow_self_approval": environment.allow_self_approval,
        },
        "config": config,
        "execution_mode": "simulated",
        "policy_version": POLICY_VERSION,
    }


def create_revision(
    db: Session,
    actor: User,
    application_id: UUID,
    data: RevisionCreate,
    request_id: str,
) -> DeploymentRevision:
    """Capture an immutable snapshot of an already-generated artifact and policy."""
    with transaction(db):
        application, binding, environment = check_delivery(
            db, actor, application_id, data.binding_id
        )
        if (
            data.expected_binding_version is not None
            and binding.version != data.expected_binding_version
        ):
            raise PolicyError(409, "stale_binding", "Binding policy has changed")
        artifact = db.scalar(
            select(Artifact).where(
                Artifact.application_id == application_id,
                Artifact.digest == data.artifact_digest,
                Artifact.kind == "generated_bundle",
            )
        )
        if artifact is None:
            raise PolicyError(
                422, "invalid_artifact", "Generate the bundle before capturing it"
            )
        if not artifact_store.exists(artifact.digest):
            raise PolicyError(
                409, "artifact_unavailable", "Artifact content is not in this store"
            )
        template = db.get(TemplateVersion, UUID(artifact.provenance["template_id"]))
        if template is None:
            raise PolicyError(
                422, "invalid_artifact", "Artifact template version is unavailable"
            )
        config = (
            data.config or SafeBindingConfig.model_validate(binding.config)
        ).model_dump()
        scope = revision_scope(artifact, template, binding, environment, config)
        revision = DeploymentRevision(
            id=uuid4(),
            application_id=application_id,
            artifact_id=artifact.id,
            artifact_digest=artifact.digest,
            template_version_id=template.id,
            binding_id=binding.id,
            binding_version=binding.version,
            bundle_target=binding.bundle_target,
            binding_snapshot=scope["binding"] | {"environment": scope["environment"]},
            config_snapshot=config,
            config_digest=canonical_digest(config),
            scope_digest=canonical_digest(scope),
            requested_by=actor.id,
            request_id=request_id,
        )
        db.add(revision)
        db.flush()
        audit_service.record_audit(
            db,
            actor,
            request_id,
            "revision.captured",
            "revision",
            revision.id,
            {
                "artifact_digest": revision.artifact_digest,
                "template": f"{template.name}@{template.version}",
                "bundle_target": revision.bundle_target,
                "binding_version": revision.binding_version,
                "config_digest": revision.config_digest,
                "scope_digest": revision.scope_digest,
                "execution_mode": revision.execution_mode,
            },
            application.id,
        )
        return revision


def get_revision(db: Session, actor: User, revision_id: UUID) -> DeploymentRevision:
    revision = db.get(DeploymentRevision, revision_id)
    if revision is None:
        raise PolicyError(404, "not_found", "Revision not found")
    get_application(db, actor, revision.application_id)
    return revision


def create_validation(
    db: Session, actor: User, revision_id: UUID, key: str, request_id: str
) -> Operation:
    """Queue an explicitly offline check of the captured artifact."""
    with transaction(db):
        payload = {
            "schema_version": 1,
            "scope": "offline",
            "revision_id": str(revision_id),
        }
        previous = replay(db, actor, "offline_validation", revision_id, key, payload)
        if previous:
            return previous
        revision = get_revision(db, actor, revision_id)
        _, binding, _ = check_delivery(
            db, actor, revision.application_id, revision.binding_id
        )
        operation = enqueue(
            db,
            actor,
            binding,
            payload,
            request_id,
            kind="offline_validation",
            execution_mode="local",
            reserve=False,
        )
        remember(db, actor, "offline_validation", revision_id, key, payload, operation)
        return operation


def visible_artifact(db: Session, actor: User, digest: str) -> Artifact:
    """Download requires current read access to an application the artifact belongs to."""
    artifacts = db.scalars(
        select(Artifact).where(Artifact.digest == digest).order_by(Artifact.created_at)
    )
    for artifact in artifacts:
        try:
            get_application(db, actor, artifact.application_id)
        except PolicyError:
            continue
        return artifact
    raise PolicyError(404, "not_found", "Artifact not found")


def load_generation_context(db: Session, operation_id: UUID) -> dict[str, Any]:
    """Read everything the handler needs, then leave the transaction behind."""
    operation = db.get(Operation, operation_id)
    assert operation is not None
    data = GenerationInput.model_validate(operation.payload)
    application = db.get(Application, operation.application_id)
    binding = db.get(EnvironmentBinding, operation.binding_id)
    assert application is not None and binding is not None
    template = get_template(data.template_name, data.template_version)
    row = db.scalar(
        select(TemplateVersion).where(
            TemplateVersion.name == template.name,
            TemplateVersion.version == template.version,
        )
    )
    if row is None or row.content_digest != template.content_digest:
        raise GenerationError(
            "template_digest_mismatch", "Template content changed after submission"
        )
    return {
        "template": template,
        "template_id": str(row.id),
        "values": template_values(template, application, binding, data),
        "application_id": application.id,
        "requested_by": operation.requested_by,
        "package_name": data.package_name,
    }


def run_generation(db: Session, operation_id: UUID) -> Handled:
    """Render, archive and store deterministically; no network, no user code."""
    context = load_generation_context(db, operation_id)
    template: Template = context["template"]
    content = build_archive(template, context["values"])
    digest, size = artifact_store.put(content)
    provenance = {
        "template_id": context["template_id"],
        "template_name": template.name,
        "template_version": template.version,
        "template_content_digest": template.content_digest,
        "parameters": context["values"],
        "parameter_digest": canonical_digest(context["values"]),
        "generation": "local_deterministic",
    }

    def apply(session: Session, operation: Operation) -> None:
        existing = session.scalar(
            select(Artifact).where(
                Artifact.application_id == operation.application_id,
                Artifact.digest == digest,
            )
        )
        if existing is None:
            session.add(
                Artifact(
                    id=uuid4(),
                    application_id=operation.application_id,
                    digest=digest,
                    storage_key=artifact_store.storage_key(digest),
                    size_bytes=size,
                    media_type=ARCHIVE_MEDIA_TYPE,
                    kind="generated_bundle",
                    provenance=provenance,
                    created_by=operation.requested_by,
                    operation_id=operation.id,
                )
            )
            session.flush()

    return "succeeded", None, apply


def load_validation_context(db: Session, operation_id: UUID) -> dict[str, Any]:
    operation = db.get(Operation, operation_id)
    assert operation is not None
    revision = db.get(DeploymentRevision, UUID(operation.payload["revision_id"]))
    assert revision is not None
    application = db.get(Application, revision.application_id)
    artifact = db.get(Artifact, revision.artifact_id)
    template = db.get(TemplateVersion, revision.template_version_id)
    binding = db.get(EnvironmentBinding, revision.binding_id)
    assert application is not None and artifact is not None and template is not None
    environment = db.get(Environment, binding.environment_id) if binding else None
    snapshot = revision.binding_snapshot.get("environment", {})
    drift = (
        binding is None
        or binding.version != revision.binding_version
        or (environment is not None and environment.version != snapshot.get("version"))
    )
    return {
        "revision_id": str(revision.id),
        "application_id": str(revision.application_id),
        "artifact_digest": revision.artifact_digest,
        "application_slug": application.slug,
        "bundle_target": revision.bundle_target,
        "config_snapshot": revision.config_snapshot,
        "scope_digest": revision.scope_digest,
        "package_name": artifact.provenance["parameters"]["package_name"],
        "required_targets": list(
            get_template(template.name, template.version).required_targets
        ),
        "template": {
            "name": template.name,
            "version": template.version,
            "content_digest": template.content_digest,
        },
        "policy_drift": drift,
    }


def run_validation(db: Session, operation_id: UUID) -> Handled:
    """Check the captured artifact offline and store the report as its own artifact."""
    context = load_validation_context(db, operation_id)
    content = artifact_store.get(context["artifact_digest"])
    report = validate_offline(content, context)
    report_bytes = canonical_json(report)
    report_digest, report_size = artifact_store.put(report_bytes)
    summary = summarise(report)

    def apply(session: Session, operation: Operation) -> None:
        artifact = session.scalar(
            select(Artifact).where(
                Artifact.application_id == operation.application_id,
                Artifact.digest == report_digest,
            )
        )
        if artifact is None:
            artifact = Artifact(
                id=uuid4(),
                application_id=operation.application_id,
                digest=report_digest,
                storage_key=artifact_store.storage_key(report_digest),
                size_bytes=report_size,
                media_type=REPORT_MEDIA_TYPE,
                kind="validation_report",
                provenance={
                    "scope": "offline",
                    "revision_id": context["revision_id"],
                    "validator": report["validator"],
                    "validator_version": report["validator_version"],
                },
                created_by=operation.requested_by,
                operation_id=operation.id,
            )
            session.add(artifact)
            session.flush()
        session.add(
            ValidationResult(
                id=uuid4(),
                revision_id=UUID(context["revision_id"]),
                application_id=operation.application_id,
                operation_id=operation.id,
                scope="offline",
                validator=report["validator"],
                validator_version=report["validator_version"],
                tool_versions=report["tool_versions"],
                result=report["result"],
                check_summary=summary,
                report_artifact_id=artifact.id,
                observed_at=now(),
                requested_by=operation.requested_by,
            )
        )
        session.flush()

    # The operation completed; whether the artifact passed is the validation result.
    return (
        "succeeded",
        None if report["result"] == "passed" else "validation_failed",
        apply,
    )


def templates() -> list[dict]:
    """The reviewed catalogue this process ships, including inactive versions."""
    return [
        {
            "name": template.name,
            "version": template.version,
            "title": template.title,
            "summary": template.summary,
            "active": template.active,
            "content_digest": template.content_digest,
            "payload_version": template.payload_version,
            "tool_versions": template.tool_versions,
            "supplied_parameters": template.supplied_parameters,
            "derived_parameters": template.derived_parameters,
            "produces": sorted(item.target for item in template.files),
        }
        for template in load_catalogue()
    ]


__all__ = [
    "POLICY_VERSION",
    "create_generation",
    "create_revision",
    "create_validation",
    "get_revision",
    "run_generation",
    "run_validation",
    "sync_template",
    "templates",
    "visible_artifact",
]
