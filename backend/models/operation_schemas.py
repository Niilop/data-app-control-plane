"""Closed simulated probe input and sanitized operation views."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from models.platform_schemas import Input, Record
from pydantic import Field, field_serializer

Status = Literal[
    "queued",
    "running",
    "retry_wait",
    "reconciling",
    "succeeded",
    "failed",
    "cancelled",
    "needs_attention",
]


class ProbeInput(Input):
    schema_version: int = Field(default=1, ge=1, le=1, strict=True)
    scenario: Literal["success", "transient", "terminal", "unknown"] = "success"
    delay_seconds: int = Field(default=0, ge=0, le=30, strict=True)


class ReconcileInput(Input):
    # A reason to inspect again, not permission to force an outcome.
    evidence: str = Field(min_length=1, max_length=500, pattern=r"\S")


class OperationResponse(Record):
    application_id: UUID
    binding_id: UUID
    binding_version: int
    requested_by: int
    kind: Literal["queue_probe"]
    execution_mode: Literal["simulated"]
    status: Status
    attempt_count: int
    max_attempts: int
    cancel_requested: bool
    diagnostic_code: str | None
    retry_of: UUID | None
    updated_at: datetime
    observed_at: datetime | None
    heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    available_at: datetime

    @field_serializer(
        "updated_at", "observed_at", "heartbeat_at", "lease_expires_at", "available_at"
    )
    def timestamp(self, value: datetime | None) -> str | None:
        return (
            value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
            if value
            else None
        )


class AttemptResponse(Record):
    phase: Literal["execute", "reconcile"]
    correlation_id: UUID
    outcome: str
    diagnostic_code: str | None
    finished_at: datetime | None

    @field_serializer("finished_at")
    def timestamp(self, value: datetime | None) -> str | None:
        return (
            value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
            if value
            else None
        )


class Accepted(Input):
    operation_id: UUID
    status: Status
    execution_mode: Literal["simulated"] = "simulated"
