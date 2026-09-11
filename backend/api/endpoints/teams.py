"""Team administration and permission-filtered membership reads."""

from typing import Annotated
from uuid import UUID

from api.dependencies import get_admin
from api.endpoints.applications import DB, Actor, Cursor, Limit
from fastapi import APIRouter, Depends, Request, Response
from models.database import User
from models.platform import AuditEvent, Team, TeamMembership
from models.platform_schemas import (
    AuditResponse,
    MemberCreate,
    MemberResponse,
    Page,
    TeamCreate,
    TeamResponse,
)
from services import application_service as service
from services.pagination import paginate
from services.policy_service import PolicyError, team_ids
from sqlalchemy import select

router = APIRouter(prefix="/api/v1", tags=["Teams"])
Admin = Annotated[User, Depends(get_admin)]


@router.get("/teams", response_model=Page[TeamResponse])
def list_teams(db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None) -> dict:
    query = select(Team)
    if not actor.is_platform_admin:
        query = query.where(Team.id.in_(team_ids(actor)))
    return paginate(db, query, Team, limit, cursor, f"teams:{actor.id}")


@router.post("/teams", response_model=TeamResponse, status_code=201)
def create_team(
    data: TeamCreate, request: Request, response: Response, db: DB, actor: Admin
) -> Team:
    team = service.create_team(db, actor, data, request.state.request_id)
    response.headers["Location"] = "/api/v1/teams"
    return team


@router.get("/teams/{team_id}/members", response_model=Page[MemberResponse])
def members(
    team_id: UUID, db: DB, actor: Actor, limit: Limit = 20, cursor: Cursor = None
) -> dict:
    query = select(Team).where(Team.id == team_id)
    if not actor.is_platform_admin:
        query = query.where(Team.id.in_(team_ids(actor)))
    if db.scalar(query) is None:
        raise PolicyError(404, "not_found", "Team not found")
    return paginate(
        db,
        select(TeamMembership).where(TeamMembership.team_id == team_id),
        TeamMembership,
        limit,
        cursor,
        f"members:{team_id}:{actor.id}",
    )


@router.post("/teams/{team_id}/members", response_model=MemberResponse, status_code=201)
def add_member(
    team_id: UUID,
    data: MemberCreate,
    request: Request,
    response: Response,
    db: DB,
    actor: Admin,
) -> TeamMembership:
    member = service.add_member(
        db, actor, team_id, data.user_id, request.state.request_id
    )
    response.headers["Location"] = f"/api/v1/teams/{team_id}/members"
    return member


@router.delete("/teams/{team_id}/members/{user_id}", status_code=204)
def remove_member(
    team_id: UUID, user_id: int, request: Request, db: DB, actor: Admin
) -> Response:
    service.remove_member(db, actor, team_id, user_id, request.state.request_id)
    return Response(status_code=204)


@router.get("/audit-events", response_model=Page[AuditResponse])
def admin_audit(db: DB, actor: Admin, limit: Limit = 20, cursor: Cursor = None) -> dict:
    return paginate(
        db, select(AuditEvent), AuditEvent, limit, cursor, f"admin-audit:{actor.id}"
    )
