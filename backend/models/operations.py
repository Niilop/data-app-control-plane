"""Durable queue metadata. No provider credentials or arbitrary executable payloads."""

from datetime import datetime
from uuid import UUID

from core.database import Base
from models.platform import Identity, utcnow
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class Operation(Identity, Base):
    __tablename__ = "operations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','retry_wait','reconciling','succeeded','failed','cancelled','needs_attention')",
            name="ck_operation_status",
        ),
        # Simulated work stands in for a provider; local work really happens here
        # and must never be labelled simulated, or the reverse.
        CheckConstraint(
            "(kind = 'queue_probe' AND execution_mode = 'simulated')"
            " OR (kind IN ('bundle_generation','offline_validation')"
            " AND execution_mode = 'local')",
            name="ck_operation_handler",
        ),
        CheckConstraint(
            "fencing_token >= 0 AND attempt_count >= 0 AND max_attempts BETWEEN 1 AND 3",
            name="ck_operation_counters",
        ),
        Index("ix_operations_queue", "status", "available_at"),
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    binding_id: Mapped[UUID] = mapped_column(ForeignKey("environment_bindings.id"))
    binding_version: Mapped[int]
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(30), default="queue_probe")
    execution_mode: Mapped[str] = mapped_column(String(30), default="simulated")
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(36))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fencing_token: Mapped[int] = mapped_column(default=0)
    attempt_count: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    diagnostic_code: Mapped[str | None] = mapped_column(String(50))
    retry_of: Mapped[UUID | None] = mapped_column(ForeignKey("operations.id"))


class OperationAttempt(Identity, Base):
    __tablename__ = "operation_attempts"
    __table_args__ = (
        UniqueConstraint("operation_id", "fencing_token", name="uq_attempt_fence"),
        CheckConstraint("phase IN ('execute','reconcile')", name="ck_attempt_phase"),
    )
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("operations.id"), index=True)
    fencing_token: Mapped[int]
    worker_id: Mapped[str] = mapped_column(String(36))
    phase: Mapped[str] = mapped_column(String(20))
    correlation_id: Mapped[UUID]
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(30), default="running")
    diagnostic_code: Mapped[str | None] = mapped_column(String(50))


class OperationReservation(Base):
    __tablename__ = "operation_reservations"
    binding_id: Mapped[UUID] = mapped_column(
        ForeignKey("environment_bindings.id"), primary_key=True
    )
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("operations.id"), unique=True)


class QueueProbe(Identity, Base):
    """Internal simulated request/result used to verify fenced related writes."""

    __tablename__ = "queue_probes"
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("operations.id"), unique=True)
    result: Mapped[str | None] = mapped_column(String(50))


class OperationCommand(Identity, Base):
    __tablename__ = "operation_commands"
    __table_args__ = (
        UniqueConstraint(
            "actor_id", "action", "target_id", "key", name="uq_operation_command"
        ),
    )
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[UUID]
    key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("operations.id"))


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
