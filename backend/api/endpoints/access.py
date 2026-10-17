"""Minimal request outcomes stay available independently of application visibility."""

from uuid import UUID

from api.endpoints.applications import DB, Actor, Cursor, Limit
from fastapi import APIRouter, Request, Response
from models.access import AccessRequest
from models.access_schemas import (
    AccessDecision,
    AccessRequestInput,
    AccessRequestResponse,
    ArchiveInput,
    EffectiveAccess,
)
from models.platform import Application
from models.platform_schemas import ApplicationResponse, Page
from services import access_service as service
from services.pagination import paginate

router = APIRouter(prefix="/api/v1", tags=["Platform access"])


@router.post(
    "/applications/{application_id}/access-requests",
    response_model=AccessRequestResponse,
    status_code=201,
)
def request_access(
    application_id: UUID,
    data: AccessRequestInput,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> AccessRequest:
    row = service.request_access(
        db, actor, application_id, data, request.state.request_id
    )
    response.headers["Location"] = f"/api/v1/access-requests/{row.id}"
    return row


@router.get("/access-requests", response_model=Page[AccessRequestResponse])
def own_requests(
    db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    return paginate(
        db,
        service.visible_requests(actor),
        AccessRequest,
        limit,
        cursor,
        f"access-requests:own:{actor.id}",
    )


@router.get(
    "/applications/{application_id}/access-requests",
    response_model=Page[AccessRequestResponse],
)
def application_requests(
    application_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    return paginate(
        db,
        service.visible_requests(actor, application_id),
        AccessRequest,
        limit,
        cursor,
        f"access-requests:{application_id}:{actor.id}",
    )


@router.get("/access-requests/{identifier}", response_model=AccessRequestResponse)
def detail(identifier: UUID, db: DB, actor: Actor) -> AccessRequest:
    return service.get_request(db, actor, identifier)


@router.post(
    "/access-requests/{identifier}/decision", response_model=AccessRequestResponse
)
def decision(
    identifier: UUID, data: AccessDecision, request: Request, db: DB, actor: Actor
) -> AccessRequest:
    return service.decide(db, actor, identifier, data, request.state.request_id)


@router.post(
    "/access-requests/{identifier}/cancel", response_model=AccessRequestResponse
)
def cancel(identifier: UUID, request: Request, db: DB, actor: Actor) -> AccessRequest:
    return service.cancel(db, actor, identifier, request.state.request_id)


@router.get(
    "/applications/{application_id}/effective-access/{user_id}",
    response_model=EffectiveAccess,
)
def effective_access(application_id: UUID, user_id: int, db: DB, actor: Actor) -> dict:
    return service.effective_access(db, actor, application_id, user_id)


@router.post(
    "/applications/{application_id}/archive", response_model=ApplicationResponse
)
def archive(
    application_id: UUID, data: ArchiveInput, request: Request, db: DB, actor: Actor
) -> Application:
    return service.archive(db, actor, application_id, data, request.state.request_id)
