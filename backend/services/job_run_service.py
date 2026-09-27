"""Operator-only, transactionally queued job runs from recorded deployments."""

from uuid import UUID

from models.database import User
from models.delivery import DeploymentRevision
from models.deployment import Deployment
from models.job_run import JobRun
from models.job_run_schemas import RunInput, RunResult
from models.operations import Operation
from models.platform import EnvironmentBinding, utcnow
from services.application_service import transaction
from services.delivery_service import enqueue as enqueue_operation
from services.deployment_service import current_revision
from services.environment_service import lock_environment
from services.operation_service import audit, remember, replay, require_operator
from services.policy_service import PolicyError, get_application
from sqlalchemy import select
from sqlalchemy.orm import Session


def get_deployment(db: Session, actor: User, identifier: UUID) -> Deployment:
    row = db.get(Deployment, identifier)
    if row is None:
        raise PolicyError(404, "not_found", "Deployment not found")
    get_application(db, actor, row.application_id)
    return row


def check_run(
    db: Session, actor: User, deployment_id: UUID, data: RunInput
) -> EnvironmentBinding:
    deployment = get_deployment(db, actor, deployment_id)
    require_operator(db, actor, get_application(db, actor, deployment.application_id))
    revision = db.get(DeploymentRevision, deployment.revision_id)
    assert revision is not None
    binding = current_revision(db, actor, revision)
    # current_revision refreshes actors/application after the policy lock wait.
    require_operator(db, actor, get_application(db, actor, deployment.application_id))
    db.refresh(deployment)
    if (
        deployment.status != "succeeded"
        or deployment.execution_mode != "simulated"
        or deployment.executor != "simulated"
        or deployment.binding_id != binding.id
        or revision.application_id != deployment.application_id
    ):
        raise PolicyError(
            409,
            "deployment_unavailable",
            "A successful simulated deployment is required",
        )
    if not any(
        r.get("resource_key") == data.resource_key
        and r.get("status") == "ready"
        and r.get("execution_mode") == "simulated"
        for r in deployment.resources
    ):
        raise PolicyError(409, "job_unavailable", "The deployed job is not ready")
    return binding


def enqueue(
    db: Session,
    actor: User,
    deployment_id: UUID,
    data: RunInput,
    request_id: str,
    retry_of: UUID | None = None,
) -> Operation:
    binding = check_run(db, actor, deployment_id, data)
    operation = enqueue_operation(
        db,
        actor,
        binding,
        "run_simulated",
        {
            "schema_version": 1,
            "deployment_id": str(deployment_id),
            **data.model_dump(mode="json"),
        },
        request_id,
        retry_of,
    )
    db.add(
        JobRun(
            application_id=binding.application_id,
            deployment_id=deployment_id,
            operation_id=operation.id,
            requested_by=actor.id,
            resource_key=data.resource_key,
            parameters=data.parameters.model_dump(),
            scenario=data.scenario,
        )
    )
    db.flush()
    audit(
        db,
        actor,
        operation,
        request_id,
        "run.submitted",
        {"deployment_id": str(deployment_id), "resource_key": data.resource_key},
    )
    return operation


def submit(
    db: Session,
    actor: User,
    deployment_id: UUID,
    data: RunInput,
    key: str,
    request_id: str,
) -> Operation:
    with transaction(db):
        deployment = get_deployment(db, actor, deployment_id)
        require_operator(
            db, actor, get_application(db, actor, deployment.application_id)
        )
        binding = db.get(EnvironmentBinding, deployment.binding_id)
        assert binding is not None
        lock_environment(db, binding.environment_id)
        db.refresh(actor)
        require_operator(
            db, actor, get_application(db, actor, deployment.application_id)
        )
        payload = data.model_dump(mode="json")
        previous = replay(db, actor, "run_simulated", deployment_id, key, payload)
        if previous:
            return previous
        operation = enqueue(db, actor, deployment_id, data, request_id)
        remember(db, actor, "run_simulated", deployment_id, key, payload, operation)
        return operation


def input_for(operation: Operation) -> tuple[UUID, RunInput]:
    if (
        operation.payload.get("schema_version") != 1
        or operation.execution_mode != "simulated"
    ):
        raise PolicyError(409, "invalid_payload", "Unsupported run payload")
    return UUID(operation.payload["deployment_id"]), RunInput.model_validate(
        {
            k: v
            for k, v in operation.payload.items()
            if k not in {"schema_version", "deployment_id"}
        }
    )


def authorize_operation(db: Session, actor: User, operation: Operation) -> None:
    deployment_id, data = input_for(operation)
    binding = check_run(db, actor, deployment_id, data)
    row = db.scalar(select(JobRun).where(JobRun.operation_id == operation.id))
    if (
        row is None
        or row.deployment_id != deployment_id
        or row.application_id != binding.application_id
        or operation.application_id != binding.application_id
        or operation.binding_id != binding.id
        or operation.binding_version != binding.version
        or row.requested_by != actor.id
        or row.resource_key != data.resource_key
        or row.parameters != data.parameters.model_dump()
        or row.scenario != data.scenario
        or row.execution_mode != "simulated"
    ):
        raise PolicyError(409, "scope_mismatch", "Run record does not match command")


def observe(
    db: Session, operation: Operation, status: str, result: RunResult | None = None
) -> None:
    row = db.scalar(select(JobRun).where(JobRun.operation_id == operation.id))
    assert row is not None
    row.status = {
        "retry_wait": "queued",
        "reconciling": "unknown",
        "needs_attention": "unknown",
    }.get(status, status)
    row.last_observed_at = utcnow()
    if result is not None:
        row.result = result.model_dump()


def verify_result(operation: Operation, result: RunResult) -> bool:
    _, data = input_for(operation)
    count = data.parameters.row_count
    return (
        data.scenario == "success"
        and result.outcome == "success"
        and result.output_verified
        and result.output == {"rows": count, "total": count * (count - 1) // 2}
    )
