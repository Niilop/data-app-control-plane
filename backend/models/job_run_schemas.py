"""Closed simulation inputs; no executable or external resource parameters."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from models.platform_schemas import Input, Record
from pydantic import Field, field_serializer


class RunParameters(Input):
    row_count: int = Field(default=100, ge=1, le=10000, strict=True)


class RunInput(Input):
    resource_key: Literal["synthetic_job"]
    parameters: RunParameters = Field(default_factory=RunParameters)
    execution_mode: Literal["simulated"]
    scenario: Literal["success", "failure"] = "success"


class RunResult(Input):
    execution_mode: Literal["simulated"] = "simulated"
    lifecycle: Literal["terminated"]
    outcome: Literal["success", "failure"]
    output: dict[str, int] | None
    output_verified: bool


class RunResponse(Record):
    application_id: UUID
    deployment_id: UUID
    operation_id: UUID
    requested_by: int
    resource_key: Literal["synthetic_job"]
    parameters: RunParameters
    scenario: Literal["success", "failure"]
    execution_mode: Literal["simulated"]
    status: Literal["queued", "running", "succeeded", "failed", "cancelled", "unknown"]
    provider_run_id: None
    result: RunResult | None
    last_observed_at: datetime | None

    @field_serializer("last_observed_at")
    def timestamp(self, value: datetime | None) -> str | None:
        return (
            value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
            if value
            else None
        )
