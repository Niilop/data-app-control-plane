"""Permission-filtered audit reads and flush-only writes; never commit."""

from uuid import UUID

from models.database import User
from models.platform import AuditEvent
from services.policy_service import get_application
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session


def visible_application_audit(db: Session, actor: User, application_id: UUID) -> Select:
    application = get_application(db, actor, application_id)
    query = select(AuditEvent).where(AuditEvent.application_id == application_id)
    if not actor.is_platform_admin and application.owner_user_id != actor.id:
        # Access-request outcomes have narrower visibility than ordinary history.
        # requested_by is the server-recorded subject, not the deciding actor.
        query = query.where(
            or_(
                AuditEvent.target_type != "access_request",
                AuditEvent.details["requested_by"].as_integer() == actor.id,
            )
        )
    return query


def record_audit(
    db: Session,
    actor: User | None,
    request_id: str,
    action: str,
    target_type: str,
    target_id: UUID | int,
    details: dict,
    application_id: UUID | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_user_id=actor.id if actor else None,
            actor_kind="user" if actor else "local_bootstrap",
            request_id=request_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            application_id=application_id,
            details=details,
        )
    )
    db.flush()
