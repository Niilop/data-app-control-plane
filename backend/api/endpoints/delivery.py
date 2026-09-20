"""Authorized preparation commands, immutable reads and verified downloads."""

from typing import Annotated
from uuid import UUID

from api.endpoints.applications import DB, Actor, Cursor, Limit
from api.endpoints.operations import Key, accepted
from fastapi import APIRouter, Path, Request, Response
from models.delivery import (
    DeploymentRevision,
    Generation,
    TemplateVersion,
    ValidationResult,
)
from models.delivery_schemas import (
    GenerationInput,
    GenerationResponse,
    RevisionInput,
    RevisionResponse,
    TemplateResponse,
    ValidationInput,
    ValidationResponse,
)
from models.operation_schemas import Accepted
from models.platform_schemas import Page
from services import delivery_service as service
from services.pagination import paginate
from services.policy_service import get_application
from sqlalchemy import select

router = APIRouter(prefix="/api/v1", tags=["Preparation"])


@router.get("/templates", response_model=list[TemplateResponse])
def templates(db: DB, actor: Actor) -> list[TemplateVersion]:
    return list(db.scalars(select(TemplateVersion).order_by(TemplateVersion.id)))


@router.post(
    "/applications/{application_id}/generations",
    status_code=202,
    response_model=Accepted,
)
def generate(
    application_id: UUID,
    data: GenerationInput,
    key: Key,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> dict:
    return accepted(
        service.generate(
            db, actor, application_id, data, key, request.state.request_id
        ),
        response,
    )


@router.get(
    "/applications/{application_id}/generations",
    response_model=Page[GenerationResponse],
)
def generations(
    application_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_application(db, actor, application_id)
    return paginate(
        db,
        select(Generation).where(Generation.application_id == application_id),
        Generation,
        limit,
        cursor,
        f"generations:{application_id}:{actor.id}",
    )


@router.get("/artifacts/{digest}")
def download(
    digest: Annotated[str, Path(pattern=r"^[a-f0-9]{64}$")], db: DB, actor: Actor
) -> Response:
    data, media_type = service.download(db, actor, digest)
    extension = "zip" if media_type == "application/zip" else "json"
    return Response(
        data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{digest}.{extension}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/applications/{application_id}/revisions",
    status_code=201,
    response_model=RevisionResponse,
)
def create_revision(
    application_id: UUID,
    data: RevisionInput,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> DeploymentRevision:
    revision = service.create_revision(
        db, actor, application_id, data, request.state.request_id
    )
    response.headers["Location"] = f"/api/v1/revisions/{revision.id}"
    return revision


@router.get(
    "/applications/{application_id}/revisions", response_model=Page[RevisionResponse]
)
def revisions(
    application_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_application(db, actor, application_id)
    return paginate(
        db,
        select(DeploymentRevision).where(
            DeploymentRevision.application_id == application_id
        ),
        DeploymentRevision,
        limit,
        cursor,
        f"revisions:{application_id}:{actor.id}",
    )


@router.get("/revisions/{revision_id}", response_model=RevisionResponse)
def revision(revision_id: UUID, db: DB, actor: Actor) -> DeploymentRevision:
    return service.get_revision(db, actor, revision_id)


@router.post(
    "/revisions/{revision_id}/validations", status_code=202, response_model=Accepted
)
def validate(
    revision_id: UUID,
    data: ValidationInput,
    key: Key,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> dict:
    return accepted(
        service.validate(db, actor, revision_id, key, request.state.request_id),
        response,
    )


@router.get(
    "/revisions/{revision_id}/validations", response_model=Page[ValidationResponse]
)
def validations(
    revision_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    service.get_revision(db, actor, revision_id)
    return paginate(
        db,
        select(ValidationResult).where(ValidationResult.revision_id == revision_id),
        ValidationResult,
        limit,
        cursor,
        f"validations:{revision_id}:{actor.id}",
    )
