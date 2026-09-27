"""Exact approval scope and explicitly simulated deployment commands/history."""

from uuid import UUID

from api.endpoints.applications import DB, Actor, Cursor, Limit
from api.endpoints.operations import Key, accepted
from fastapi import APIRouter, Request, Response
from models.deployment import Approval, Deployment
from models.deployment_schemas import (
    ApprovalInput,
    ApprovalResponse,
    DeploymentInput,
    DeploymentResponse,
    ScopeResponse,
)
from models.operation_schemas import Accepted
from models.platform_schemas import Page
from services import deployment_service as service
from services.delivery_service import get_revision
from services.pagination import paginate
from services.policy_service import PolicyError, get_application
from services.template_service import canonical, sha
from sqlalchemy import select

router = APIRouter(prefix="/api/v1", tags=["Simulated deployment"])


@router.get("/revisions/{revision_id}/approval-scope", response_model=ScopeResponse)
def scope(revision_id: UUID, validation_id: UUID, db: DB, actor: Actor) -> dict:
    revision = get_revision(db, actor, revision_id)
    evidence = service.scope_for(db, revision, validation_id)
    return {"scope_digest": sha(canonical(evidence)), "scope": evidence}


@router.post(
    "/revisions/{revision_id}/approvals",
    status_code=201,
    response_model=ApprovalResponse,
)
def approve(
    revision_id: UUID,
    data: ApprovalInput,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> Approval:
    row = service.approve(db, actor, revision_id, data, request.state.request_id)
    response.headers["Location"] = f"/api/v1/revisions/{revision_id}/approvals"
    return row


@router.get("/revisions/{revision_id}/approvals", response_model=Page[ApprovalResponse])
def approvals(
    revision_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_revision(db, actor, revision_id)
    return paginate(
        db,
        select(Approval).where(Approval.revision_id == revision_id),
        Approval,
        limit,
        cursor,
        f"approvals:{revision_id}:{actor.id}",
    )


@router.post(
    "/applications/{application_id}/deployments",
    status_code=202,
    response_model=Accepted,
)
def deploy(
    application_id: UUID,
    data: DeploymentInput,
    key: Key,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> dict:
    return accepted(
        service.submit(db, actor, application_id, data, key, request.state.request_id),
        response,
    )


@router.get(
    "/applications/{application_id}/deployments",
    response_model=Page[DeploymentResponse],
)
def deployments(
    application_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_application(db, actor, application_id)
    return paginate(
        db,
        select(Deployment).where(Deployment.application_id == application_id),
        Deployment,
        limit,
        cursor,
        f"deployments:{application_id}:{actor.id}",
    )


@router.get(
    "/applications/{application_id}/bindings/{binding_id}/last-success",
    response_model=DeploymentResponse | None,
)
def last_success(
    application_id: UUID, binding_id: UUID, db: DB, actor: Actor
) -> Deployment | None:
    get_application(db, actor, application_id)
    return db.scalar(
        select(Deployment)
        .where(
            Deployment.application_id == application_id,
            Deployment.binding_id == binding_id,
            Deployment.status == "succeeded",
        )
        .order_by(Deployment.last_observed_at.desc(), Deployment.id.desc())
        .limit(1)
    )


@router.get("/deployments/{deployment_id}", response_model=DeploymentResponse)
def deployment(deployment_id: UUID, db: DB, actor: Actor) -> Deployment:
    row = db.get(Deployment, deployment_id)
    if row is None:
        raise PolicyError(404, "not_found", "Deployment not found")
    get_application(db, actor, row.application_id)
    return row
