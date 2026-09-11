"""Template catalogue, generation, artifact download, revisions and validation."""

from uuid import UUID

from api.endpoints.applications import DB, Actor, Cursor, Limit
from api.endpoints.operations import Key, accepted
from fastapi import APIRouter, Request, Response
from integrations import artifact_store
from models.delivery import Artifact, DeploymentRevision, ValidationResult
from models.delivery_schemas import (
    ArtifactResponse,
    GenerationInput,
    RevisionCreate,
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

router = APIRouter(prefix="/api/v1", tags=["Delivery"])


@router.get("/templates", response_model=list[TemplateResponse])
def templates(actor: Actor) -> list[dict]:
    """Reviewed template versions and their input contract; no application data."""
    return service.templates()


@router.post(
    "/applications/{application_id}/generations",
    response_model=Accepted,
    status_code=202,
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
        service.create_generation(
            db, actor, application_id, data, key, request.state.request_id
        ),
        response,
    )


@router.get(
    "/applications/{application_id}/artifacts", response_model=Page[ArtifactResponse]
)
def artifacts(
    application_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_application(db, actor, application_id)
    return paginate(
        db,
        select(Artifact).where(Artifact.application_id == application_id),
        Artifact,
        limit,
        cursor,
        f"artifacts:{application_id}:{actor.id}",
    )


@router.get("/artifacts/{digest}")
def download(digest: str, db: DB, actor: Actor) -> Response:
    """Authorized by an associated application; storage layout stays opaque."""
    artifact = service.visible_artifact(db, actor, digest)
    content = artifact_store.get(artifact.digest)
    extension = "zip" if artifact.kind == "generated_bundle" else "json"
    return Response(
        content=content,
        media_type=artifact.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.digest[:16]}.{extension}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Artifact-Digest": artifact.digest,
        },
    )


@router.post(
    "/applications/{application_id}/revisions",
    response_model=RevisionResponse,
    status_code=201,
)
def capture_revision(
    application_id: UUID,
    data: RevisionCreate,
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
def revision_detail(revision_id: UUID, db: DB, actor: Actor) -> DeploymentRevision:
    return service.get_revision(db, actor, revision_id)


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


@router.post(
    "/revisions/{revision_id}/validations", response_model=Accepted, status_code=202
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
    """Offline scope only. This never becomes, or is displayed as, workspace validation."""
    return accepted(
        service.create_validation(
            db, actor, revision_id, key, request.state.request_id
        ),
        response,
    )
