"""Central policy used by API and future application/worker services."""

from uuid import UUID

from models.database import User
from models.platform import Application, ApplicationRole, TeamMembership
from sqlalchemy import Select, exists, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement


class PolicyError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)


def require_active(actor: User) -> None:
    if not actor.is_active:
        raise PolicyError(403, "inactive_actor", "Account is inactive")


def require_admin(actor: User) -> None:
    require_active(actor)
    if not actor.is_platform_admin:
        raise PolicyError(403, "forbidden", "Platform administrator required")


def team_ids(actor: User) -> Select:
    return select(TeamMembership.team_id).where(TeamMembership.user_id == actor.id)


def role_filter(actor: User) -> ColumnElement[bool]:
    return or_(
        ApplicationRole.user_id == actor.id,
        ApplicationRole.team_id.in_(team_ids(actor)),
    )


def visible_applications(actor: User) -> Select:
    require_active(actor)
    query = select(Application)
    if actor.is_platform_admin:
        return query
    return query.where(
        or_(
            Application.owner_user_id == actor.id,
            Application.data_owner_user_id == actor.id,
            exists(
                select(ApplicationRole.id).where(
                    ApplicationRole.application_id == Application.id, role_filter(actor)
                )
            ),
        )
    )


def get_application(db: Session, actor: User, application_id: UUID) -> Application:
    application = db.scalar(
        visible_applications(actor).where(Application.id == application_id)
    )
    if application is None:
        raise PolicyError(404, "not_found", "Application not found")
    return application


def require_manager(actor: User, application: Application) -> None:
    require_active(actor)
    if not actor.is_platform_admin and application.owner_user_id != actor.id:
        raise PolicyError(
            403, "forbidden", "Application owner or platform administrator required"
        )


def require_developer(db: Session, actor: User, application: Application) -> None:
    require_active(actor)
    if (
        db.scalar(
            select(ApplicationRole.id)
            .where(
                ApplicationRole.application_id == application.id,
                ApplicationRole.role == "developer",
                role_filter(actor),
            )
            .limit(1)
        )
        is None
    ):
        raise PolicyError(403, "forbidden", "Developer role required")


def require_member(db: Session, actor: User, team_id: UUID) -> None:
    require_active(actor)
    if (
        db.scalar(
            select(TeamMembership.id).where(
                TeamMembership.team_id == team_id, TeamMembership.user_id == actor.id
            )
        )
        is None
    ):
        raise PolicyError(403, "forbidden", "Membership in the owning team is required")
