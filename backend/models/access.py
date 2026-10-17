"""Platform access requests; grants remain ordinary application roles."""

from datetime import datetime
from uuid import UUID

from core.database import Base
from models.platform import Identity
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column


class AccessRequest(Identity, Base):
    __tablename__ = "access_requests"
    __table_args__ = (
        CheckConstraint(
            "requested_role IN ('viewer','developer','approver','operator')",
            name="ck_access_request_role",
        ),
        CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled')",
            name="ck_access_request_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND decided_by IS NULL AND decided_at IS NULL "
            "AND decision_reason IS NULL) OR (status <> 'pending' "
            "AND decided_by IS NOT NULL AND decided_at IS NOT NULL "
            "AND decision_reason IS NOT NULL)",
            name="ck_access_request_decision",
        ),
        Index(
            "uq_pending_access_request",
            "application_id",
            "requested_by",
            "requested_role",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    # Own-access only: the requester is also the subject of the requested role.
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    requested_role: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decision_reason: Mapped[str | None] = mapped_column(String(2000))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
