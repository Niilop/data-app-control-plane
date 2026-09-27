"""Closed simulated commands and public approval/deployment views."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from models.platform_schemas import Input, Record
from pydantic import Field


class ApprovalInput(Input):
    validation_id: UUID
    scope_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=1, max_length=500)
    acknowledge_local_self_approval: bool = False


class ApprovalResponse(Record):
    revision_id: UUID
    validation_id: UUID
    scope_digest: str
    scope: dict
    approver_id: int
    decision: Literal["approved", "rejected"]
    reason: str
    policy_version: str
    self_approval_acknowledged: bool


class ScopeResponse(Input):
    scope_digest: str
    scope: dict


class DeploymentInput(Input):
    revision_id: UUID
    approval_id: UUID
    binding_id: UUID
    execution_mode: Literal["simulated"]
    scenario: Literal["success", "partial_failure"] = "success"


class DeploymentResponse(Record):
    application_id: UUID
    binding_id: UUID
    revision_id: UUID
    approval_id: UUID
    operation_id: UUID
    requested_by: int
    executor: Literal["simulated"]
    execution_mode: Literal["simulated"]
    scenario: Literal["success", "partial_failure"]
    status: str
    resources: list[dict]
    last_observed_at: datetime | None
