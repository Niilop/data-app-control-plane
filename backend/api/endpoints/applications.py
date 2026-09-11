"""Authenticated application registry and history endpoints."""

from typing import Annotated
from uuid import UUID

from api.dependencies import get_actor
from core.database import get_db
from fastapi import APIRouter, Depends, Query, Request, Response
from models.database import User
from models.platform import Application, ApplicationRole, AuditEvent
from models.platform_schemas import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationUpdate,
    AuditResponse,
    Page,
    RoleCreate,
    RoleResponse,
)
from services import application_service as service
from services.pagination import paginate
from services.policy_service import get_application, visible_applications
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/applications", tags=["Applications"])
DB = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_actor)]
Limit = Annotated[int, Query(ge=1, le=100)]
Cursor = Annotated[str | None, Query(max_length=1000)]


@router.post("", response_model=ApplicationResponse, status_code=201)
def create(
    data: ApplicationCreate, request: Request, response: Response, db: DB, actor: Actor
) -> Application:
    application = service.create_application(db, actor, data, request.state.request_id)
    response.headers["Location"] = f"/api/v1/applications/{application.id}"
    return application


@router.get("", response_model=Page[ApplicationResponse])
def list_applications(
    db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    return paginate(
        db,
        visible_applications(actor),
        Application,
        limit,
        cursor,
        f"applications:{actor.id}",
    )


@router.get("/{application_id}", response_model=ApplicationResponse)
def detail(application_id: UUID, db: DB, actor: Actor) -> Application:
    return get_application(db, actor, application_id)


@router.patch("/{application_id}", response_model=ApplicationResponse)
def update(
    application_id: UUID,
    data: ApplicationUpdate,
    request: Request,
    db: DB,
    actor: Actor,
) -> Application:
    return service.update_application(
        db, actor, application_id, data, request.state.request_id
    )


@router.get("/{application_id}/roles", response_model=Page[RoleResponse])
def roles(
    application_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_application(db, actor, application_id)
    return paginate(
        db,
        select(ApplicationRole).where(ApplicationRole.application_id == application_id),
        ApplicationRole,
        limit,
        cursor,
        f"roles:{application_id}:{actor.id}",
    )


@router.post("/{application_id}/roles", response_model=RoleResponse, status_code=201)
def assign_role(
    application_id: UUID,
    data: RoleCreate,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> ApplicationRole:
    role = service.assign_role(
        db, actor, application_id, data, request.state.request_id
    )
    response.headers["Location"] = f"/api/v1/applications/{application_id}/roles"
    return role


@router.delete("/{application_id}/roles/{assignment_id}", status_code=204)
def remove_role(
    application_id: UUID, assignment_id: UUID, request: Request, db: DB, actor: Actor
) -> Response:
    service.remove_role(
        db, actor, application_id, assignment_id, request.state.request_id
    )
    return Response(status_code=204)


@router.get("/{application_id}/audit-events", response_model=Page[AuditResponse])
def audit(
    application_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_application(db, actor, application_id)
    return paginate(
        db,
        select(AuditEvent).where(AuditEvent.application_id == application_id),
        AuditEvent,
        limit,
        cursor,
        f"audit:{application_id}:{actor.id}",
    )
