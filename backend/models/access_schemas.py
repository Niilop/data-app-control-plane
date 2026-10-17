"""Closed own-access commands and minimal request outcomes."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from models.platform_schemas import Input, Record, Role
from pydantic import BaseModel, Field, field_serializer

Reason = Annotated[str, Field(min_length=1, max_length=2000, pattern=r"\S")]


class AccessRequestInput(Input):
    requested_role: Role
    reason: Reason


class AccessDecision(Input):
    decision: Literal["approved", "rejected"]
    reason: Reason


class ArchiveInput(Input):
    expected_version: Annotated[int, Field(strict=True, ge=1)]


class AccessRequestResponse(Record):
    application_id: UUID
    requested_by: int
    requested_role: Role
    reason: str
    status: Literal["pending", "approved", "rejected", "cancelled"]
    decided_by: int | None
    decision_reason: str | None
    decided_at: datetime | None

    @field_serializer("decided_at")
    def timestamp(self, value: datetime | None) -> str | None:
        return (
            value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
            if value
            else None
        )


class EffectiveGrant(BaseModel):
    assignment_id: UUID
    role: Role
    team_id: UUID | None


class EffectiveAccess(BaseModel):
    user_id: int
    is_active: bool
    can_read: bool
    roles: list[Role]
    relationships: list[str]
    grants: list[EffectiveGrant]
