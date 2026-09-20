"""Exact-scope approvals and explicitly simulated deployment history."""

from datetime import datetime
from uuid import UUID

from core.database import Base
from models.delivery import immutable
from models.platform import Identity
from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, event
from sqlalchemy.orm import Mapped, mapped_column


class Approval(Identity, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approved','rejected')", name="ck_approval_decision"
        ),
    )
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("deployment_revisions.id"), index=True
    )
    validation_id: Mapped[UUID] = mapped_column(ForeignKey("validation_results.id"))
    scope_digest: Mapped[str] = mapped_column(String(64))
    scope: Mapped[dict] = mapped_column(JSON)
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(500))
    policy_version: Mapped[str] = mapped_column(String(30))
    self_approval_acknowledged: Mapped[bool]


class Deployment(Identity, Base):
    __tablename__ = "deployments"
    __table_args__ = (
        CheckConstraint(
            "execution_mode = 'simulated' AND executor = 'simulated'",
            name="ck_deployment_mode",
        ),
        CheckConstraint(
            "status IN ('queued','deploying','succeeded','failed','unknown','cancelled')",
            name="ck_deployment_status",
        ),
        CheckConstraint(
            "scenario IN ('success','partial_failure')", name="ck_deployment_scenario"
        ),
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    binding_id: Mapped[UUID] = mapped_column(ForeignKey("environment_bindings.id"))
    revision_id: Mapped[UUID] = mapped_column(ForeignKey("deployment_revisions.id"))
    approval_id: Mapped[UUID] = mapped_column(ForeignKey("approvals.id"))
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("operations.id"), unique=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    executor: Mapped[str] = mapped_column(String(30), default="simulated")
    execution_mode: Mapped[str] = mapped_column(String(30), default="simulated")
    scenario: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    resources: Mapped[list] = mapped_column(JSON, default=list)
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


for action in ("before_update", "before_delete"):
    event.listen(Approval, action, immutable)
