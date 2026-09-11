"""Authorized queue reads and typed recovery actions, never arbitrary submission."""

from datetime import timedelta
from typing import Annotated
from uuid import UUID

from api.endpoints.applications import DB, Actor, Cursor, Limit
from api.endpoints.teams import Admin
from fastapi import APIRouter, Header, Request, Response
from models.operation_schemas import (
    Accepted,
    AttemptResponse,
    OperationResponse,
    ReconcileInput,
)
from models.operations import Operation, OperationAttempt, WorkerHeartbeat
from models.platform_schemas import Page
from services.operation_service import command, get_operation
from services.pagination import paginate
from services.policy_service import get_application
from services.queue_service import now
from sqlalchemy import func, select

router = APIRouter(prefix="/api/v1", tags=["Operations"])
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


@router.get("/operations/{operation_id}", response_model=OperationResponse)
def detail(operation_id: UUID, db: DB, actor: Actor) -> Operation:
    return get_operation(db, actor, operation_id)


@router.get(
    "/applications/{application_id}/operations", response_model=Page[OperationResponse]
)
def operations(
    application_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_application(db, actor, application_id)
    return paginate(
        db,
        select(Operation).where(Operation.application_id == application_id),
        Operation,
        limit,
        cursor,
        f"operations:{application_id}:{actor.id}",
    )


@router.get("/operations/{operation_id}/attempts", response_model=Page[AttemptResponse])
def attempts(
    operation_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_operation(db, actor, operation_id)
    return paginate(
        db,
        select(OperationAttempt).where(OperationAttempt.operation_id == operation_id),
        OperationAttempt,
        limit,
        cursor,
        f"attempts:{operation_id}:{actor.id}",
    )


def accepted(operation: Operation, response: Response) -> dict:
    response.headers["Location"] = f"/api/v1/operations/{operation.id}"
    return {
        "operation_id": operation.id,
        "status": operation.status,
        "execution_mode": operation.execution_mode,
    }


@router.post(
    "/operations/{operation_id}/cancel", response_model=Accepted, status_code=202
)
def cancel(
    operation_id: UUID,
    key: Key,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> dict:
    return accepted(
        command(db, actor, operation_id, "cancel", key, request.state.request_id, {}),
        response,
    )


@router.post(
    "/operations/{operation_id}/retry", response_model=Accepted, status_code=202
)
def retry(
    operation_id: UUID,
    key: Key,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> dict:
    return accepted(
        command(db, actor, operation_id, "retry", key, request.state.request_id, {}),
        response,
    )


@router.post(
    "/operations/{operation_id}/reconcile", response_model=Accepted, status_code=202
)
def reconcile(
    operation_id: UUID,
    data: ReconcileInput,
    key: Key,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> dict:
    return accepted(
        command(
            db,
            actor,
            operation_id,
            "reconcile",
            key,
            request.state.request_id,
            data.model_dump(),
        ),
        response,
    )


@router.get("/queue/telemetry")
def telemetry(db: DB, actor: Admin) -> dict:
    timestamp = now(db)
    counts = {
        status: count
        for status, count in db.execute(
            select(Operation.status, func.count()).group_by(Operation.status)
        ).all()
    }
    oldest = db.scalar(
        select(func.min(Operation.available_at)).where(
            Operation.status.in_(["queued", "retry_wait", "reconciling"]),
            Operation.worker_id.is_(None),
            Operation.available_at <= timestamp,
        )
    )
    from services.queue_service import aware

    return {
        "execution_mode": "simulated",
        "observed_at": timestamp.isoformat(),
        "counts": counts,
        "oldest_eligible_age_seconds": max(
            0, (timestamp - aware(oldest)).total_seconds()
        )
        if oldest
        else None,
        "live_workers": db.scalar(
            select(func.count())
            .select_from(WorkerHeartbeat)
            .where(WorkerHeartbeat.seen_at >= timestamp - timedelta(seconds=60))
        ),
        "expired_leases": db.scalar(
            select(func.count())
            .select_from(Operation)
            .where(
                Operation.worker_id.is_not(None),
                Operation.lease_expires_at <= timestamp,
            )
        ),
    }
