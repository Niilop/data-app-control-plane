"""Bounded source commands, without URLs or credentials supplied by callers."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from models.platform_schemas import Input, Record
from pydantic import Field, field_serializer, field_validator


class SourceInput(Input):
    binding_id: UUID
    expected_binding_version: int = Field(ge=1, strict=True)
    ref: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_./-]+$")
    template_id: Literal["python-batch:1.0.0"] = "python-batch:1.0.0"

    @field_validator("ref")
    @classmethod
    def valid_ref(cls, value: str) -> str:
        if any(part in {"", ".", ".."} for part in value.split("/")) or ".." in value:
            raise ValueError("Use a branch, tag or commit reference")
        return value


class SourceResponse(Record):
    application_id: UUID
    operation_id: UUID
    repository_url: str
    bundle_root: str
    requested_ref: str
    binding_snapshot: dict
    template_id: str
    template_digest: str
    repository_id: int | None
    commit_sha: str | None
    artifact_digest: str | None
    captured_at: datetime | None

    @field_serializer("captured_at")
    def serialize_captured(self, value: datetime | None) -> str | None:
        return (
            value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
            if value
            else None
        )


class CIResponse(Record):
    application_id: UUID
    source_capture_id: UUID
    operation_id: UUID
    commit_sha: str
    run_id: int
    run_attempt: int
    workflow_id: int
    status: str
    conclusion: str | None
    event: str
    url: str
    observed_at: datetime

    @field_serializer("observed_at")
    def serialize_observed(self, value: datetime) -> str:
        return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
