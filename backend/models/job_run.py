"""Job observations are separate from deployment outcomes."""

from datetime import datetime
from uuid import UUID

from core.database import Base
from models.platform import Identity
from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class JobRun(Identity, Base):
    __tablename__ = "job_runs"
    __table_args__ = (
        CheckConstraint("execution_mode = 'simulated'", name="ck_job_run_mode"),
        CheckConstraint("resource_key = 'synthetic_job'", name="ck_job_run_resource"),
        CheckConstraint(
            "scenario IN ('success','failure')", name="ck_job_run_scenario"
        ),
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled','unknown')",
            name="ck_job_run_status",
        ),
        CheckConstraint("provider_run_id IS NULL", name="ck_job_run_no_provider"),
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    deployment_id: Mapped[UUID] = mapped_column(
        ForeignKey("deployments.id"), index=True
    )
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("operations.id"), unique=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    resource_key: Mapped[str] = mapped_column(String(50))
    parameters: Mapped[dict] = mapped_column(JSON)
    scenario: Mapped[str] = mapped_column(String(20))
    execution_mode: Mapped[str] = mapped_column(String(30), default="simulated")
    status: Mapped[str] = mapped_column(String(30), default="queued")
    provider_run_id: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
