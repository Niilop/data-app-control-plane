"""Recorded run reads and an allowlisted simulated run command."""

from uuid import UUID

from api.endpoints.applications import DB, Actor, Cursor, Limit
from api.endpoints.operations import Key, accepted
from fastapi import APIRouter, Request, Response
from models.job_run import JobRun
from models.job_run_schemas import RunInput, RunResponse
from models.operation_schemas import Accepted
from models.platform_schemas import Page
from services import job_run_service as service
from services.pagination import paginate
from services.policy_service import PolicyError, get_application
from sqlalchemy import select

router = APIRouter(prefix="/api/v1", tags=["Simulated job runs"])


@router.post(
    "/deployments/{deployment_id}/runs", status_code=202, response_model=Accepted
)
def submit(
    deployment_id: UUID,
    data: RunInput,
    key: Key,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> dict:
    return accepted(
        service.submit(db, actor, deployment_id, data, key, request.state.request_id),
        response,
    )


@router.get("/deployments/{deployment_id}/runs", response_model=Page[RunResponse])
def deployment_runs(
    deployment_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    service.get_deployment(db, actor, deployment_id)
    return paginate(
        db,
        select(JobRun).where(JobRun.deployment_id == deployment_id),
        JobRun,
        limit,
        cursor,
        f"deployment-runs:{deployment_id}:{actor.id}",
    )


@router.get("/applications/{application_id}/runs", response_model=Page[RunResponse])
def application_runs(
    application_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_application(db, actor, application_id)
    return paginate(
        db,
        select(JobRun).where(JobRun.application_id == application_id),
        JobRun,
        limit,
        cursor,
        f"application-runs:{application_id}:{actor.id}",
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
def run(run_id: UUID, db: DB, actor: Actor) -> JobRun:
    row = db.get(JobRun, run_id)
    if row is None:
        raise PolicyError(404, "not_found", "Run not found")
    get_application(db, actor, row.application_id)
    return row
