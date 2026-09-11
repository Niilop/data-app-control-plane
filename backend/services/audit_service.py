"""Audit helpers flush inside the caller's transaction; never commit."""

from uuid import UUID

from models.database import User
from models.platform import AuditEvent
from sqlalchemy.orm import Session


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
