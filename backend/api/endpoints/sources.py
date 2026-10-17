"""Source adoption commands and recorded GitHub observations; GET never calls GitHub."""

from uuid import UUID

from api.endpoints.applications import DB, Actor, Cursor, Limit
from api.endpoints.operations import Key, accepted
from fastapi import APIRouter, Request, Response
from models.operation_schemas import Accepted
from models.platform_schemas import Input, Page
from models.source import CIRun, SourceCapture
from models.source_schemas import CIResponse, SourceInput, SourceResponse
from services import source_service as service
from services.pagination import paginate
from services.policy_service import get_application
from sqlalchemy import select

router = APIRouter(prefix="/api/v1", tags=["GitHub source"])


@router.get("/applications/{application_id}/ci-onboarding")
def onboarding(application_id: UUID, db: DB, actor: Actor) -> Response:
    from services.ci_onboarding import render

    app = get_application(db, actor, application_id)
    return Response(
        render(app.bundle_root),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="ci-onboarding.zip"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/applications/{application_id}/source-policy")
def policy(application_id: UUID, db: DB, actor: Actor) -> dict:
    return {
        "enabled": service.enabled(get_application(db, actor, application_id)),
        "execution_mode": "github_read",
    }


@router.post(
    "/applications/{application_id}/source-captures",
    status_code=202,
    response_model=Accepted,
)
def capture(
    application_id: UUID,
    data: SourceInput,
    key: Key,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> dict:
    return accepted(
        service.capture(db, actor, application_id, data, key, request.state.request_id),
        response,
    )


@router.get(
    "/applications/{application_id}/source-captures",
    response_model=Page[SourceResponse],
)
def captures(
    application_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_application(db, actor, application_id)
    return paginate(
        db,
        select(SourceCapture).where(SourceCapture.application_id == application_id),
        SourceCapture,
        limit,
        cursor,
        f"sources:{application_id}:{actor.id}",
    )


@router.post(
    "/source-captures/{capture_id}/ci-refresh", status_code=202, response_model=Accepted
)
def refresh(
    capture_id: UUID,
    data: Input,
    key: Key,
    request: Request,
    response: Response,
    db: DB,
    actor: Actor,
) -> dict:
    return accepted(
        service.refresh(db, actor, capture_id, key, request.state.request_id), response
    )


@router.get("/applications/{application_id}/ci-runs", response_model=Page[CIResponse])
def runs(
    application_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    get_application(db, actor, application_id)
    return paginate(
        db,
        select(CIRun).where(CIRun.application_id == application_id),
        CIRun,
        limit,
        cursor,
        f"ci:{application_id}:{actor.id}",
    )
