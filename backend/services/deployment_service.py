"""Approval evidence and simulated deployment transactions; no provider calls."""

from uuid import UUID

from models.database import User
from models.delivery import DeploymentRevision, ValidationResult
from models.deployment import Approval, Deployment
from models.deployment_schemas import ApprovalInput, DeploymentInput
from models.operations import Operation
from models.platform import ApplicationRole, EnvironmentBinding, utcnow
from services import delivery_service as preparation
from services.application_service import transaction
from services.audit_service import record_audit
from services.environment_service import lock_environment, require_target
from services.operation_service import remember, replay, require_operator
from services.policy_service import (
    PolicyError,
    get_application,
    require_active,
    require_developer,
    role_filter,
)
from services.template_service import canonical, sha
from sqlalchemy import select
from sqlalchemy.orm import Session

POLICY_VERSION = "local-simulation-v1"


def require_approver(db: Session, actor: User, application_id: UUID) -> None:
    require_active(actor)
    if (
        db.scalar(
            select(ApplicationRole.id)
            .where(
                ApplicationRole.application_id == application_id,
                ApplicationRole.role == "approver",
                role_filter(actor),
            )
            .limit(1)
        )
        is None
    ):
        raise PolicyError(403, "forbidden", "Approver role required")


def scope_for(db: Session, revision: DeploymentRevision, validation_id: UUID) -> dict:
    report = db.get(ValidationResult, validation_id)
    if (
        report is None
        or report.revision_id != revision.id
        or report.result != "passed"
        or report.scope != "offline"
    ):
        raise PolicyError(
            409,
            "invalid_validation",
            "A passed offline report for this exact revision is required",
        )
    return {
        "policy_version": POLICY_VERSION,
        "application_id": str(revision.application_id),
        "revision_id": str(revision.id),
        "source_kind": revision.source_kind,
        "artifact_digest": revision.artifact_digest,
        "template_id": revision.template_id,
        "template_digest": revision.template_digest,
        "config_digest": revision.config_digest,
        "config": revision.config_snapshot,
        "binding": revision.binding_snapshot,
        "execution_mode": "simulated",
        "executor": "simulated",
        "validation": {
            "id": str(report.id),
            "report_digest": report.report_digest,
            "scope": report.scope,
            "validator_version": report.validator_version,
            "result": report.result,
        },
    }


def current_revision(
    db: Session, actor: User, revision: DeploymentRevision
) -> EnvironmentBinding:
    from core.config import get_settings
    from services.environment_service import require_local_simulation

    require_local_simulation(get_settings())
    app = get_application(db, actor, revision.application_id)
    if app.lifecycle == "archived":
        raise PolicyError(409, "archived", "Application is archived")
    binding = db.get(EnvironmentBinding, revision.binding_id)
    assert binding is not None
    environment = lock_environment(db, binding.environment_id)
    # Refresh eligibility after a potentially blocking policy lock.
    db.refresh(actor)
    require_active(actor)
    db.refresh(app)
    if app.lifecycle == "archived":
        raise PolicyError(409, "archived", "Application is archived")
    db.refresh(binding)
    require_target(environment, binding.bundle_target)
    if preparation.snapshot(db, binding) != revision.binding_snapshot:
        raise PolicyError(
            409,
            "stale_revision",
            "Binding policy changed; prepare and approve a new revision",
        )
    approved = preparation.template(db)
    if (
        revision.template_id != approved.id
        or revision.template_digest != approved.content_digest
    ):
        raise PolicyError(409, "invalid_template", "Template contract changed")
    return binding


def self_policy(
    revision: DeploymentRevision,
    approver_id: int,
    requester_id: int,
    acknowledged: bool,
) -> None:
    if approver_id in {revision.requested_by, requester_id} and (
        not revision.binding_snapshot["allow_self_approval"] or not acknowledged
    ):
        raise PolicyError(
            403,
            "self_approval_denied",
            "Local self-approval requires enabled policy and explicit acknowledgement",
        )


def approve(
    db: Session, actor: User, revision_id: UUID, data: ApprovalInput, request_id: str
) -> Approval:
    with transaction(db):
        revision = preparation.get_revision(db, actor, revision_id)
        require_approver(db, actor, revision.application_id)
        current_revision(db, actor, revision)
        require_approver(db, actor, revision.application_id)
        scope = scope_for(db, revision, data.validation_id)
        if sha(canonical(scope)) != data.scope_digest:
            raise PolicyError(
                409,
                "scope_mismatch",
                "Approval scope does not match this revision and report",
            )
        if data.decision == "approved":
            self_policy(
                revision,
                actor.id,
                revision.requested_by,
                data.acknowledge_local_self_approval,
            )
        row = Approval(
            revision_id=revision.id,
            validation_id=data.validation_id,
            scope_digest=data.scope_digest,
            scope=scope,
            approver_id=actor.id,
            decision=data.decision,
            reason=data.reason,
            policy_version=POLICY_VERSION,
            self_approval_acknowledged=data.acknowledge_local_self_approval,
        )
        db.add(row)
        db.flush()
        record_audit(
            db,
            actor,
            request_id,
            "approval.recorded",
            "approval",
            row.id,
            {
                "decision": row.decision,
                "scope_digest": row.scope_digest,
                "execution_mode": "simulated",
                "local_self_approval": actor.id == revision.requested_by,
                "self_approval_acknowledged": row.self_approval_acknowledged,
                "policy_version": POLICY_VERSION,
            },
            revision.application_id,
        )
        return row


def check_approval(
    db: Session, actor: User, application_id: UUID, data: DeploymentInput
) -> EnvironmentBinding:
    app = get_application(db, actor, application_id)
    require_developer(db, actor, app)
    require_operator(db, actor, app)
    revision = preparation.get_revision(db, actor, data.revision_id)
    if (
        revision.application_id != application_id
        or revision.binding_id != data.binding_id
    ):
        raise PolicyError(
            409, "scope_mismatch", "Revision does not match application and binding"
        )
    binding = current_revision(db, actor, revision)
    require_developer(db, actor, app)
    require_operator(db, actor, app)
    approval = db.get(Approval, data.approval_id)
    if (
        approval is None
        or approval.revision_id != revision.id
        or approval.decision != "approved"
        or approval.policy_version != POLICY_VERSION
    ):
        raise PolicyError(409, "approval_required", "Exact revision approval required")
    latest = db.scalar(
        select(Approval.id)
        .where(
            Approval.revision_id == revision.id,
            Approval.scope_digest == approval.scope_digest,
        )
        .order_by(Approval.created_at.desc(), Approval.id.desc())
        .limit(1)
    )
    if latest != approval.id:
        raise PolicyError(
            409, "approval_superseded", "A newer decision exists for this exact scope"
        )
    scope = scope_for(db, revision, approval.validation_id)
    if approval.scope != scope or approval.scope_digest != sha(canonical(scope)):
        raise PolicyError(409, "scope_mismatch", "Approval evidence does not match")
    approver = db.get(User, approval.approver_id, populate_existing=True)
    if approver is None:
        raise PolicyError(403, "inactive_actor", "Approver unavailable")
    require_approver(db, approver, application_id)
    self_policy(revision, approver.id, actor.id, approval.self_approval_acknowledged)
    return binding


def enqueue(
    db: Session,
    actor: User,
    application_id: UUID,
    data: DeploymentInput,
    request_id: str,
    retry_of: UUID | None = None,
) -> Operation:
    binding = check_approval(db, actor, application_id, data)
    payload = {"schema_version": 1, **data.model_dump(mode="json")}
    operation = preparation.enqueue(
        db, actor, binding, "deploy_simulated", payload, request_id, retry_of
    )
    db.add(
        Deployment(
            application_id=application_id,
            binding_id=binding.id,
            revision_id=data.revision_id,
            approval_id=data.approval_id,
            operation_id=operation.id,
            requested_by=actor.id,
            scenario=data.scenario,
        )
    )
    db.flush()
    approval = db.get(Approval, data.approval_id)
    assert approval is not None
    record_audit(
        db,
        actor,
        request_id,
        "deployment.submitted",
        "operation",
        operation.id,
        {
            "approval_id": str(approval.id),
            "scope_digest": approval.scope_digest,
            "execution_mode": "simulated",
            "scenario": data.scenario,
            "submitter_is_approver": actor.id == approval.approver_id,
            "self_approval_acknowledged": approval.self_approval_acknowledged,
        },
        application_id,
    )
    return operation


def submit(
    db: Session,
    actor: User,
    application_id: UUID,
    data: DeploymentInput,
    key: str,
    request_id: str,
) -> Operation:
    with transaction(db):
        app = get_application(db, actor, application_id)
        require_developer(db, actor, app)
        require_operator(db, actor, app)
        binding = db.get(EnvironmentBinding, data.binding_id)
        if binding is None or binding.application_id != application_id:
            raise PolicyError(422, "invalid_binding", "Binding is unavailable")
        lock_environment(db, binding.environment_id)
        payload = data.model_dump(mode="json")
        previous = replay(db, actor, "deploy_simulated", application_id, key, payload)
        if previous:
            return previous
        operation = enqueue(db, actor, application_id, data, request_id)
        remember(db, actor, "deploy_simulated", application_id, key, payload, operation)
        return operation


def input_for(operation: Operation) -> DeploymentInput:
    if (
        operation.payload.get("schema_version") != 1
        or operation.execution_mode != "simulated"
    ):
        raise PolicyError(409, "invalid_payload", "Unsupported deployment payload")
    return DeploymentInput.model_validate(
        {k: v for k, v in operation.payload.items() if k != "schema_version"}
    )


def authorize_operation(db: Session, actor: User, operation: Operation) -> None:
    data = input_for(operation)
    binding = check_approval(db, actor, operation.application_id, data)
    row = db.scalar(select(Deployment).where(Deployment.operation_id == operation.id))
    if (
        row is None
        or row.revision_id != data.revision_id
        or row.approval_id != data.approval_id
        or row.binding_id != binding.id
        or operation.binding_id != binding.id
        or operation.binding_version != binding.version
        or row.requested_by != actor.id
        or row.scenario != data.scenario
    ):
        raise PolicyError(
            409, "scope_mismatch", "Deployment record does not match command"
        )


def observe(
    db: Session, operation: Operation, status: str, resources: list | None = None
) -> None:
    row = db.scalar(select(Deployment).where(Deployment.operation_id == operation.id))
    assert row is not None
    row.status = {
        "running": "deploying",
        "retry_wait": "queued",
        "reconciling": "unknown",
        "needs_attention": "unknown",
    }.get(status, status)
    row.last_observed_at = utcnow()
    if resources is not None:
        row.resources = resources
    if status == "succeeded":
        actor = db.get(User, operation.requested_by)
        assert actor is not None
        app = get_application(db, actor, operation.application_id)
        # Atomic SQL avoids lost metadata/version updates across independent bindings.
        from models.platform import Application
        from sqlalchemy import update

        db.execute(
            update(Application)
            .where(Application.id == app.id, Application.lifecycle == "registered")
            .values(lifecycle="active", version=Application.version + 1)
        )
