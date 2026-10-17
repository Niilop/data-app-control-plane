"""Own-access workflow, effective grant explanations and archival transactions."""

from uuid import UUID

from models.access import AccessRequest
from models.access_schemas import AccessDecision, AccessRequestInput, ArchiveInput
from models.database import User
from models.operations import Operation, OperationReservation
from models.platform import Application, ApplicationRole, utcnow
from services.application_service import active_user, transaction
from services.audit_service import record_audit
from services.policy_service import (
    PolicyError,
    get_application,
    lock_application,
    mutable_application,
    require_active,
    require_manager,
    require_unarchived,
    role_filter,
)
from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session


def visible_requests(actor: User, application_id: UUID | None = None) -> Select:
    require_active(actor)
    query = select(AccessRequest)
    if application_id is None:
        # The global inbox always shows only the caller's requests, including admins.
        return query.where(AccessRequest.requested_by == actor.id)
    query = query.where(AccessRequest.application_id == application_id)
    if not actor.is_platform_admin:
        managed = select(Application.id).where(Application.owner_user_id == actor.id)
        query = query.where(
            or_(
                AccessRequest.requested_by == actor.id,
                AccessRequest.application_id.in_(managed),
            )
        )
    return query


def get_request(db: Session, actor: User, identifier: UUID) -> AccessRequest:
    row = db.get(AccessRequest, identifier)
    if row is None:
        raise PolicyError(404, "not_found", "Access request not found")
    found = db.scalar(
        visible_requests(actor, row.application_id).where(
            AccessRequest.id == identifier
        )
    )
    if found is None:
        raise PolicyError(404, "not_found", "Access request not found")
    return found


def request_access(
    db: Session,
    actor: User,
    application_id: UUID,
    data: AccessRequestInput,
    request_id: str,
) -> AccessRequest:
    with transaction(db):
        app = lock_application(db, application_id)
        db.refresh(actor)
        require_active(actor)
        require_unarchived(app)
        existing = db.scalar(
            select(AccessRequest).where(
                AccessRequest.application_id == application_id,
                AccessRequest.requested_by == actor.id,
                AccessRequest.requested_role == data.requested_role,
                AccessRequest.status == "pending",
            )
        )
        if existing:
            if existing.reason != data.reason:
                raise PolicyError(
                    409, "request_pending", "A request for this role is already pending"
                )
            return existing
        row = AccessRequest(
            application_id=application_id, requested_by=actor.id, **data.model_dump()
        )
        db.add(row)
        db.flush()
        record_audit(
            db,
            actor,
            request_id,
            "access.requested",
            "access_request",
            row.id,
            {"requested_role": row.requested_role, "requested_by": actor.id},
            application_id,
        )
        return row


def resolve(
    db: Session,
    actor: User,
    row: AccessRequest,
    status: str,
    reason: str,
    request_id: str,
) -> None:
    """Flush-only helper: decision, role insertion and audit belong to the caller."""
    row.status = status
    row.decided_by = actor.id
    row.decided_at = utcnow()
    row.decision_reason = reason
    record_audit(
        db,
        actor,
        request_id,
        f"access.{status}",
        "access_request",
        row.id,
        {
            "requested_by": row.requested_by,
            "requested_role": row.requested_role,
            "reason": reason,
        },
        row.application_id,
    )


def decide(
    db: Session, actor: User, identifier: UUID, data: AccessDecision, request_id: str
) -> AccessRequest:
    with transaction(db):
        row = get_request(db, actor, identifier)
        app = lock_application(db, row.application_id)
        db.refresh(actor)
        require_manager(actor, app)
        db.refresh(row)
        if row.status != "pending":
            if row.status == data.decision and row.decision_reason == data.reason:
                # Historical replay never re-grants a subsequently revoked assignment.
                return row
            raise PolicyError(
                409, "request_resolved", "Access request is already resolved"
            )
        require_unarchived(app)
        if data.decision == "approved":
            active_user(db, row.requested_by)
            existing = db.scalar(
                select(ApplicationRole).where(
                    ApplicationRole.application_id == row.application_id,
                    ApplicationRole.user_id == row.requested_by,
                    ApplicationRole.role == row.requested_role,
                )
            )
            if existing is None:
                db.add(
                    ApplicationRole(
                        application_id=row.application_id,
                        user_id=row.requested_by,
                        role=row.requested_role,
                    )
                )
        resolve(db, actor, row, data.decision, data.reason, request_id)
        return row


def cancel(
    db: Session, actor: User, identifier: UUID, request_id: str
) -> AccessRequest:
    with transaction(db):
        row = get_request(db, actor, identifier)
        lock_application(db, row.application_id)
        db.refresh(actor)
        require_active(actor)
        if row.requested_by != actor.id:
            raise PolicyError(
                403, "forbidden", "Only the requester can withdraw a request"
            )
        db.refresh(row)
        if row.status == "cancelled":
            return row
        if row.status != "pending":
            raise PolicyError(
                409, "request_resolved", "Access request is already resolved"
            )
        resolve(db, actor, row, "cancelled", "Withdrawn by requester", request_id)
        return row


def effective_access(
    db: Session, actor: User, application_id: UUID, user_id: int
) -> dict:
    app = get_application(db, actor, application_id)
    if user_id != actor.id:
        require_manager(actor, app)
    subject = db.get(User, user_id)
    if subject is None:
        raise PolicyError(404, "not_found", "User not found")
    grants = list(
        db.scalars(
            select(ApplicationRole)
            .where(
                ApplicationRole.application_id == application_id, role_filter(subject)
            )
            .order_by(ApplicationRole.role, ApplicationRole.id)
        )
    )
    relationships = []
    if app.owner_user_id == user_id:
        relationships.append("application_owner")
    if app.data_owner_user_id == user_id:
        relationships.append("data_owner")
    if subject.is_platform_admin:
        relationships.append("platform_admin")
    return {
        "user_id": user_id,
        "is_active": subject.is_active,
        "can_read": subject.is_active and bool(grants or relationships),
        "roles": sorted({grant.role for grant in grants}) if subject.is_active else [],
        "relationships": relationships,
        "grants": [
            {"assignment_id": grant.id, "role": grant.role, "team_id": grant.team_id}
            for grant in grants
        ],
    }


def archive(
    db: Session, actor: User, application_id: UUID, data: ArchiveInput, request_id: str
) -> Application:
    with transaction(db):
        app = mutable_application(db, actor, application_id)
        require_manager(actor, app)
        if app.version != data.expected_version:
            raise PolicyError(
                409, "stale_version", "Application changed; reload before archiving"
            )
        unresolved = db.scalar(
            select(Operation.id)
            .where(
                Operation.application_id == application_id,
                or_(
                    Operation.status.not_in(("succeeded", "failed", "cancelled")),
                    Operation.id.in_(select(OperationReservation.operation_id)),
                ),
            )
            .limit(1)
        )
        if unresolved is not None:
            raise PolicyError(
                409,
                "unresolved_work",
                "Resolve all application operations before archiving",
            )
        for row in db.scalars(
            select(AccessRequest).where(
                AccessRequest.application_id == application_id,
                AccessRequest.status == "pending",
            )
        ):
            resolve(db, actor, row, "cancelled", "Application archived", request_id)
        app.lifecycle = "archived"
        app.version += 1
        app.updated_at = utcnow()
        record_audit(
            db,
            actor,
            request_id,
            "application.archived",
            "application",
            app.id,
            {"version": app.version},
            app.id,
        )
        return app
