"""Short database transactions implement leases and fence every result write."""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from models.database import User
from models.operations import Operation, OperationAttempt, QueueProbe, WorkerHeartbeat
from services.operation_service import audit, check_execution, release
from services.policy_service import PolicyError
from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.orm import Session

Outcome = Literal[
    "succeeded", "transient", "failed", "cancelled", "unknown", "safe_to_retry"
]


class LostLease(Exception):
    """Caller must discard all results and stop handling the claim."""


@dataclass(frozen=True)
class Claim:
    operation_id: UUID
    worker_id: str
    token: int
    phase: str
    kind: str
    payload: dict
    attempt_count: int


def now(db: Session) -> datetime:
    # PostgreSQL transaction timestamps are stale after waiting for a row lock.
    if db.get_bind().dialect.name == "postgresql":
        timestamp = db.scalar(select(func.clock_timestamp()))
        assert timestamp is not None
        return timestamp
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=value.tzinfo or timezone.utc)


def worker_seen(db: Session, worker_id: str) -> None:
    heartbeat = db.get(WorkerHeartbeat, worker_id)
    if heartbeat is None:
        db.add(WorkerHeartbeat(worker_id=worker_id, seen_at=now(db)))
    else:
        heartbeat.seen_at = now(db)


def claim(
    db: Session,
    worker_id: str,
    lease_seconds: int = 30,
    kinds: tuple[str, ...] | None = None,
) -> Claim | None:
    with db.begin():
        worker_seen(db, worker_id)
        timestamp = now(db)
        operation = db.scalar(
            select(Operation)
            .where(Operation.kind.in_(kinds) if kinds else true())
            .where(
                or_(
                    and_(
                        Operation.status.in_(["queued", "retry_wait", "reconciling"]),
                        Operation.worker_id.is_(None),
                        Operation.available_at <= timestamp,
                    ),
                    and_(
                        Operation.status.in_(["running", "reconciling"]),
                        Operation.lease_expires_at <= timestamp,
                    ),
                )
            )
            .order_by(Operation.available_at, Operation.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if operation is None:
            return None
        expired = operation.worker_id is not None
        phase = (
            "reconcile" if expired or operation.status == "reconciling" else "execute"
        )
        if expired:
            old = db.scalar(
                select(OperationAttempt).where(
                    OperationAttempt.operation_id == operation.id,
                    OperationAttempt.fencing_token == operation.fencing_token,
                )
            )
            if old:
                old.finished_at = now(db)
                old.outcome = "lease_expired"
                old.diagnostic_code = "lease_expired"
        operation.fencing_token += 1
        if phase == "execute":
            operation.attempt_count += 1
        operation.status = "reconciling" if phase == "reconcile" else "running"
        operation.worker_id = worker_id
        operation.heartbeat_at = now(db)
        operation.lease_expires_at = operation.heartbeat_at + timedelta(
            seconds=lease_seconds
        )
        operation.updated_at = operation.heartbeat_at
        db.add(
            OperationAttempt(
                operation_id=operation.id,
                fencing_token=operation.fencing_token,
                worker_id=worker_id,
                phase=phase,
                correlation_id=uuid4(),
            )
        )
        actor = db.get(User, operation.requested_by)
        assert actor is not None
        audit(
            db,
            actor,
            operation,
            operation.request_id,
            "operation.claimed",
            {
                "worker_id": worker_id,
                "fencing_token": operation.fencing_token,
                "phase": phase,
            },
        )
        return Claim(
            operation.id,
            worker_id,
            operation.fencing_token,
            phase,
            operation.kind,
            operation.payload,
            operation.attempt_count,
        )


def owned(db: Session, item: Claim) -> Operation:
    operation = db.scalar(
        select(Operation)
        .where(Operation.id == item.operation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        operation is None
        or operation.worker_id != item.worker_id
        or operation.fencing_token != item.token
        or operation.status not in {"running", "reconciling"}
        or operation.lease_expires_at is None
        or aware(operation.lease_expires_at) <= now(db)
    ):
        raise LostLease()
    return operation


def heartbeat(db: Session, item: Claim, lease_seconds: int = 30) -> bool:
    with db.begin():
        operation = owned(db, item)
        operation.heartbeat_at = now(db)
        operation.lease_expires_at = operation.heartbeat_at + timedelta(
            seconds=lease_seconds
        )
        worker_seen(db, item.worker_id)
        return operation.cancel_requested


def authorize(db: Session, item: Claim) -> None:
    with db.begin():
        operation = owned(db, item)
        actor = db.get(User, operation.requested_by)
        if actor is None:
            raise PolicyError(403, "inactive_actor", "Requester unavailable")
        if operation.kind == "queue_probe":
            check_execution(
                db,
                actor,
                operation.application_id,
                operation.binding_id,
                operation.binding_version,
            )
        else:
            from services.delivery_service import authorize_operation

            authorize_operation(db, actor, operation)
        # Policy locks can wait; recheck the lease after acquiring them.
        owned(db, item)


def finish(
    db: Session,
    item: Claim,
    outcome: Outcome,
    *,
    diagnostic: str | None = None,
    delivery_result: tuple[str, int, str, str] | None = None,
) -> None:
    """Operation, attempt, related result, reservation and audit commit together."""
    with db.begin():
        operation = owned(db, item)
        timestamp = now(db)
        assert operation.lease_expires_at is not None
        deadline = aware(operation.lease_expires_at)
        attempt = db.scalar(
            select(OperationAttempt).where(
                OperationAttempt.operation_id == item.operation_id,
                OperationAttempt.fencing_token == item.token,
            )
        )
        assert attempt is not None
        code = diagnostic
        if outcome in {"transient", "safe_to_retry"}:
            if operation.cancel_requested:
                status = "cancelled"
            elif operation.attempt_count >= operation.max_attempts:
                status, code = "failed", "retry_exhausted"
            else:
                status = "retry_wait"
                delay = min(60, 2**operation.attempt_count)
                operation.available_at = timestamp + timedelta(
                    seconds=delay * random.uniform(0.8, 1.2)
                )
                code = "safe_retry_scheduled"
        elif outcome == "unknown":
            status = "needs_attention" if item.phase == "reconcile" else "reconciling"
            code = "outcome_unknown"
            operation.available_at = timestamp
        else:
            status = outcome
        if status == "succeeded" and operation.kind != "queue_probe":
            from services.delivery_service import authorize_operation, record_result

            actor = db.get(User, operation.requested_by)
            assert actor is not None
            try:
                authorize_operation(db, actor, operation)
            except PolicyError:
                status, code = "failed", "authorization_changed"
            else:
                if delivery_result is None:
                    raise ValueError("Missing delivery result")
                record_result(db, operation, delivery_result)
        operation.status = status
        operation.diagnostic_code = code
        operation.observed_at = timestamp
        operation.updated_at = timestamp
        operation.worker_id = None
        operation.lease_expires_at = None
        attempt.finished_at = timestamp
        attempt.outcome = status
        attempt.diagnostic_code = code
        if status in {"succeeded", "failed", "cancelled"}:
            probe = db.scalar(
                select(QueueProbe).where(QueueProbe.operation_id == operation.id)
            )
            if operation.kind == "queue_probe":
                assert probe is not None
                probe.result = status
            release(db, operation)
        actor = db.get(User, operation.requested_by)
        assert actor is not None
        audit(
            db,
            actor,
            operation,
            operation.request_id,
            "operation.observed",
            {
                "worker_id": item.worker_id,
                "fencing_token": item.token,
                "status": status,
                "diagnostic_code": code,
            },
        )
        # Audit flushes related changes as well. Roll everything back if a slow
        # statement consumed the remaining lease while this row was locked.
        if now(db) >= deadline:
            raise LostLease()
