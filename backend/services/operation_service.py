"""Transactional commands for the durable queue; no handler runs in the API."""

import hashlib
import json
import re
from uuid import UUID, uuid4

from core.config import get_settings
from models.database import User
from models.operation_schemas import ProbeInput
from models.operations import (
    Operation,
    OperationCommand,
    OperationReservation,
    QueueProbe,
)
from models.platform import Application, ApplicationRole, EnvironmentBinding, utcnow
from services import audit_service
from services.application_service import transaction
from services.environment_service import (
    lock_environment,
    require_local_simulation,
    require_target,
)
from services.policy_service import (
    PolicyError,
    get_application,
    require_active,
    role_filter,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

TERMINAL = {"succeeded", "failed", "cancelled"}


def require_operator(db: Session, actor: User, application: Application) -> None:
    require_active(actor)
    if (
        db.scalar(
            select(ApplicationRole.id)
            .where(
                ApplicationRole.application_id == application.id,
                ApplicationRole.role == "operator",
                role_filter(actor),
            )
            .limit(1)
        )
        is None
    ):
        raise PolicyError(403, "forbidden", "Operator role required")


def get_operation(
    db: Session, actor: User, operation_id: UUID, *, lock: bool = False
) -> Operation:
    query = select(Operation).where(Operation.id == operation_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    operation = db.scalar(query)
    if operation is None:
        raise PolicyError(404, "not_found", "Operation not found")
    get_application(db, actor, operation.application_id)
    return operation


def check_execution(
    db: Session,
    actor: User,
    application_id: UUID,
    binding_id: UUID,
    version: int | None = None,
) -> EnvironmentBinding:
    require_local_simulation(get_settings())
    application = get_application(db, actor, application_id)
    require_operator(db, actor, application)
    if application.lifecycle == "archived":
        raise PolicyError(409, "archived", "Application is archived")
    binding = db.get(EnvironmentBinding, binding_id)
    if binding is None or binding.application_id != application_id:
        raise PolicyError(422, "invalid_binding", "Binding is unavailable")
    environment = lock_environment(db, binding.environment_id)
    db.refresh(binding)
    require_target(environment, binding.bundle_target)
    if version is not None and binding.version != version:
        raise PolicyError(409, "stale_binding", "Binding policy has changed")
    return binding


def digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def replay(
    db: Session, actor: User, action: str, target: UUID, key: str, payload: dict
) -> Operation | None:
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", key):
        raise PolicyError(
            422, "invalid_idempotency_key", "Supply a 1–128 character Idempotency-Key"
        )
    command = db.scalar(
        select(OperationCommand).where(
            OperationCommand.actor_id == actor.id,
            OperationCommand.action == action,
            OperationCommand.target_id == target,
            OperationCommand.key == key,
        )
    )
    if command is None:
        return None
    if command.payload_hash != digest(payload):
        raise PolicyError(
            409, "idempotency_conflict", "Key was used with a different payload"
        )
    return db.get(Operation, command.operation_id)


def remember(
    db: Session,
    actor: User,
    action: str,
    target: UUID,
    key: str,
    payload: dict,
    operation: Operation,
) -> None:
    db.add(
        OperationCommand(
            actor_id=actor.id,
            action=action,
            target_id=target,
            key=key,
            payload_hash=digest(payload),
            operation_id=operation.id,
        )
    )
    db.flush()


def audit(
    db: Session,
    actor: User,
    operation: Operation,
    request_id: str,
    action: str,
    details: dict | None = None,
) -> None:
    audit_service.record_audit(
        db,
        actor,
        request_id,
        action,
        "operation",
        operation.id,
        {
            "operation_id": str(operation.id),
            "execution_mode": operation.execution_mode,
            **(details or {}),
        },
        operation.application_id,
    )


def create_probe(
    db: Session,
    actor: User,
    application_id: UUID,
    binding_id: UUID,
    data: ProbeInput,
    key: str,
    request_id: str,
) -> Operation:
    """Internal CLI/service entry only. Locks binding to serialize commands and reservations."""
    with transaction(db):
        # Lock order: environment then binding, shared with environment administration.
        require_operator(db, actor, get_application(db, actor, application_id))
        binding = db.get(EnvironmentBinding, binding_id)
        if binding is None or binding.application_id != application_id:
            raise PolicyError(422, "invalid_binding", "Binding is unavailable")
        lock_environment(db, binding.environment_id)
        db.scalar(
            select(EnvironmentBinding)
            .where(EnvironmentBinding.id == binding.id)
            .with_for_update()
        )
        payload = data.model_dump()
        previous = replay(db, actor, "queue_probe", binding_id, key, payload)
        if previous:
            return previous
        binding = check_execution(db, actor, application_id, binding_id)
        operation = enqueue(db, actor, binding, payload, request_id)
        remember(db, actor, "queue_probe", binding_id, key, payload, operation)
        return operation


def enqueue(
    db: Session,
    actor: User,
    binding: EnvironmentBinding,
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
        requested_by=actor.id,
        request_id=request_id,
        payload=payload,
        retry_of=retry_of,
    )
    db.add(operation)
    db.flush()
    db.add_all(
        [
            QueueProbe(operation_id=operation.id),
            OperationReservation(binding_id=binding.id, operation_id=operation.id),
        ]
    )
    audit(db, actor, operation, request_id, "operation.queued")
    return operation


def command(
    db: Session,
    actor: User,
    operation_id: UUID,
    action: str,
    key: str,
    request_id: str,
    payload: dict,
) -> Operation:
    with transaction(db):
        operation = get_operation(db, actor, operation_id, lock=True)
        require_operator(
            db, actor, get_application(db, actor, operation.application_id)
        )
        previous = replay(db, actor, action, operation_id, key, payload)
        if previous:
            return previous
        result = operation
        if action == "cancel":
            if operation.status not in TERMINAL:
                operation.cancel_requested = True
                if operation.status in {"queued", "retry_wait"}:
                    operation.status = "cancelled"
                    probe = db.scalar(
                        select(QueueProbe).where(
                            QueueProbe.operation_id == operation.id
                        )
                    )
                    if operation.kind == "queue_probe":
                        assert probe is not None
                        probe.result = "cancelled"
                    release(db, operation)
        elif action == "retry":
            if operation.status not in {"failed", "cancelled"}:
                raise PolicyError(
                    409,
                    "unsafe_retry",
                    "Only resolved failures or cancellations can be retried",
                )
            if operation.kind == "queue_probe":
                binding = check_execution(
                    db, actor, operation.application_id, operation.binding_id
                )
                result = enqueue(
                    db, actor, binding, operation.payload, request_id, operation.id
                )
            else:
                from services.delivery_service import retry_operation

                result = retry_operation(db, actor, operation, request_id)
        elif action == "reconcile":
            if operation.status != "needs_attention":
                raise PolicyError(
                    409,
                    "invalid_state",
                    "Only operations needing attention can be reconciled",
                )
            operation.status = "reconciling"
            operation.available_at = utcnow()
        else:
            raise ValueError("Unsupported operation command")
        operation.updated_at = utcnow()
        # Store only a digest of operator evidence, which could contain pasted secrets.
        audit(
            db,
            actor,
            operation,
            request_id,
            f"operation.{action}",
            {"evidence_hash": digest(payload)} if payload else {},
        )
        remember(db, actor, action, operation_id, key, payload, result)
        return result


def release(db: Session, operation: Operation) -> None:
    reservation = db.get(OperationReservation, operation.binding_id)
    if reservation and reservation.operation_id == operation.id:
        db.delete(reservation)
