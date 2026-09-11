"""Environment administration and authorized binding reads."""

from uuid import UUID

from api.endpoints.applications import DB, Actor, Cursor, Limit
from api.endpoints.teams import Admin
from fastapi import APIRouter, Request, Response
from models.environment_schemas import (
    BindingCreate,
    BindingResponse,
    BindingUpdate,
    EnvironmentCreate,
    EnvironmentResponse,
    EnvironmentUpdate,
)
from models.platform import Environment, EnvironmentBinding
from models.platform_schemas import Page
from services import environment_service as service
from services.pagination import paginate
from services.policy_service import PolicyError, get_application
from sqlalchemy import select

router = APIRouter(prefix="/api/v1", tags=["Environments"])


@router.post("/environments", response_model=EnvironmentResponse, status_code=201)
def create_environment(
    data: EnvironmentCreate, request: Request, response: Response, db: DB, actor: Admin
) -> Environment:
    environment = service.create_environment(db, actor, data, request.state.request_id)
    response.headers["Location"] = f"/api/v1/environments/{environment.id}"
    return environment


@router.get("/environments", response_model=Page[EnvironmentResponse])
def environments(
    db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    return paginate(
        db,
        service.visible_environments(actor),
        Environment,
        limit,
        cursor,
        f"environments:{actor.id}",
    )


@router.get("/environments/{environment_id}", response_model=EnvironmentResponse)
def environment_detail(environment_id: UUID, db: DB, actor: Actor) -> Environment:
    return service.get_environment(db, actor, environment_id)


@router.patch("/environments/{environment_id}", response_model=EnvironmentResponse)
def update_environment(
    environment_id: UUID,
    data: EnvironmentUpdate,
    request: Request,
    db: DB,
    actor: Admin,
) -> Environment:
    return service.update_environment(
        db, actor, environment_id, data, request.state.request_id
    )


@router.post(
    "/applications/{application_id}/bindings",
    response_model=BindingResponse,
    status_code=201,
)
def create_binding(
    application_id: UUID,
    data: BindingCreate,
    request: Request,
    response: Response,
    db: DB,
    actor: Admin,
) -> BindingResponse:
    binding = service.create_binding(
        db, actor, application_id, data, request.state.request_id
    )
    response.headers["Location"] = (
        f"/api/v1/applications/{application_id}/bindings/{binding.id}"
    )
    return service.binding_response(db, binding)


@router.get(
    "/applications/{application_id}/bindings", response_model=Page[BindingResponse]
)
def bindings(
    application_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_application(db, actor, application_id)
    result = paginate(
        db,
        select(EnvironmentBinding).where(
            EnvironmentBinding.application_id == application_id
        ),
        EnvironmentBinding,
        limit,
        cursor,
        f"bindings:{application_id}:{actor.id}",
    )
    result["items"] = [
        service.binding_response(db, binding) for binding in result["items"]
    ]
    return result


@router.get(
    "/applications/{application_id}/bindings/{binding_id}",
    response_model=BindingResponse,
)
def binding_detail(
    application_id: UUID, binding_id: UUID, db: DB, actor: Actor
) -> BindingResponse:
    get_application(db, actor, application_id)
    binding = db.scalar(
        select(EnvironmentBinding).where(
            EnvironmentBinding.id == binding_id,
            EnvironmentBinding.application_id == application_id,
        )
    )
    if binding is None:
        raise PolicyError(404, "not_found", "Binding not found")
    return service.binding_response(db, binding)


@router.patch(
    "/applications/{application_id}/bindings/{binding_id}",
    response_model=BindingResponse,
)
def update_binding(
    application_id: UUID,
    binding_id: UUID,
    data: BindingUpdate,
    request: Request,
    db: DB,
    actor: Admin,
) -> BindingResponse:
    binding = service.update_binding(
        db, actor, application_id, binding_id, data, request.state.request_id
    )
    return service.binding_response(db, binding)
