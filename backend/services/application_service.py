"""Registry commands own one transaction, including their success audit."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from models.database import User
from models.platform import Application, ApplicationRole, Team, TeamMembership, utcnow
from models.platform_schemas import (
    ApplicationCreate,
    ApplicationUpdate,
    RoleCreate,
    TeamCreate,
)
from services import audit_service
from services.policy_service import (
    PolicyError,
    get_application,
    require_admin,
    require_developer,
    require_manager,
    require_member,
)
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@contextmanager
def transaction(db: Session) -> Iterator[None]:
    """Include dependency reads in the service transaction; roll back every failure."""
    try:
        yield
        db.commit()
    except IntegrityError:
        db.rollback()
        raise PolicyError(
            409,
            "registry_conflict",
            "Registry change conflicts with an existing record",
        ) from None
    except Exception:
        db.rollback()
        raise


def active_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise PolicyError(
            422, "invalid_user", "Referenced user must exist and be active"
        )
    return user


def known_team(db: Session, team_id: UUID) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise PolicyError(422, "invalid_team", "Referenced team does not exist")
    return team


def create_team(db: Session, actor: User, data: TeamCreate, request_id: str) -> Team:
    with transaction(db):
        require_admin(actor)
        team = Team(name=data.name)
        db.add(team)
        db.flush()
        audit_service.record_audit(
            db, actor, request_id, "team.created", "team", team.id, {"name": team.name}
        )
    return team


def add_member(
    db: Session, actor: User, team_id: UUID, user_id: int, request_id: str
) -> TeamMembership:
    with transaction(db):
        require_admin(actor)
        known_team(db, team_id)
        active_user(db, user_id)
        member = TeamMembership(team_id=team_id, user_id=user_id)
        db.add(member)
        db.flush()
        audit_service.record_audit(
            db,
            actor,
            request_id,
            "team.member_added",
            "team",
            team_id,
            {"user_id": user_id},
        )
    return member


def remove_member(
    db: Session, actor: User, team_id: UUID, user_id: int, request_id: str
) -> None:
    with transaction(db):
        require_admin(actor)
        member = db.scalar(
            select(TeamMembership).where(
                TeamMembership.team_id == team_id, TeamMembership.user_id == user_id
            )
        )
        if member is None:
            raise PolicyError(404, "not_found", "Membership not found")
        db.delete(member)
        audit_service.record_audit(
            db,
            actor,
            request_id,
            "team.member_removed",
            "team",
            team_id,
            {"user_id": user_id},
        )


def create_application(
    db: Session, actor: User, data: ApplicationCreate, request_id: str
) -> Application:
    with transaction(db):
        # Even a platform admin must belong to the owning team to register.
        known_team(db, data.owning_team_id)
        require_member(db, actor, data.owning_team_id)
        active_user(db, data.owner_user_id)
        active_user(db, data.data_owner_user_id)
        application = Application(**data.model_dump(), created_by=actor.id)
        db.add(application)
        db.flush()
        for role in ("developer", "viewer"):
            db.add(
                ApplicationRole(
                    application_id=application.id, user_id=actor.id, role=role
                )
            )
        audit_service.record_audit(
            db,
            actor,
            request_id,
            "application.registered",
            "application",
            application.id,
            {
                **data.model_dump(mode="json"),
                "initial_roles": ["developer", "viewer"],
                "role_user_id": actor.id,
                "repository_verified": False,
            },
            application.id,
        )
    return application


def update_application(
    db: Session,
    actor: User,
    application_id: UUID,
    data: ApplicationUpdate,
    request_id: str,
) -> Application:
    with transaction(db):
        application = get_application(db, actor, application_id)
        if application.lifecycle == "archived":
            raise PolicyError(
                409, "application_archived", "Archived applications cannot be changed"
            )
        changes = data.model_dump(exclude_unset=True, exclude={"expected_version"})
        ownership = {"owning_team_id", "owner_user_id", "data_owner_user_id"}
        if ownership & changes.keys():
            require_manager(actor, application)
        if changes.keys() - ownership:
            require_developer(db, actor, application)
        if "owning_team_id" in changes:
            known_team(db, changes["owning_team_id"])
        for field in ("owner_user_id", "data_owner_user_id"):
            if field in changes:
                active_user(db, changes[field])
        before = {
            field: str(getattr(application, field))
            if field == "owning_team_id"
            else getattr(application, field)
            for field in changes
        }
        if {"repository_url", "bundle_root"} & changes.keys():
            changes["repository_verified_at"] = None
        result = db.execute(
            update(Application)
            .where(
                Application.id == application_id,
                Application.version == data.expected_version,
            )
            .values(**changes, version=Application.version + 1, updated_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise PolicyError(
                409, "stale_version", "Application changed; reload before saving"
            )
        audit_service.record_audit(
            db,
            actor,
            request_id,
            "application.updated",
            "application",
            application_id,
            {
                "before": before,
                "after": data.model_dump(
                    mode="json", exclude_unset=True, exclude={"expected_version"}
                ),
                "version": data.expected_version + 1,
            },
            application_id,
        )
        db.refresh(application)
    return application


def assign_role(
    db: Session, actor: User, application_id: UUID, data: RoleCreate, request_id: str
) -> ApplicationRole:
    with transaction(db):
        application = get_application(db, actor, application_id)
        require_manager(actor, application)
        if data.user_id is not None:
            active_user(db, data.user_id)
        if data.team_id is not None:
            known_team(db, data.team_id)
        assignment = ApplicationRole(application_id=application_id, **data.model_dump())
        db.add(assignment)
        db.flush()
        audit_service.record_audit(
            db,
            actor,
            request_id,
            "application.role_assigned",
            "application_role",
            assignment.id,
            data.model_dump(mode="json"),
            application_id,
        )
    return assignment


def remove_role(
    db: Session, actor: User, application_id: UUID, assignment_id: UUID, request_id: str
) -> None:
    with transaction(db):
        application = get_application(db, actor, application_id)
        require_manager(actor, application)
        assignment = db.scalar(
            select(ApplicationRole).where(
                ApplicationRole.id == assignment_id,
                ApplicationRole.application_id == application_id,
            )
        )
        if assignment is None:
            raise PolicyError(404, "not_found", "Role assignment not found")
        details = {
            "role": assignment.role,
            "user_id": assignment.user_id,
            "team_id": str(assignment.team_id) if assignment.team_id else None,
        }
        db.delete(assignment)
        audit_service.record_audit(
            db,
            actor,
            request_id,
            "application.role_removed",
            "application_role",
            assignment_id,
            details,
            application_id,
        )
