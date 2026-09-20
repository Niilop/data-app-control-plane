"""Closed preparation inputs and public, storage-free resource views."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from models.platform_schemas import Input, Record
from pydantic import Field


class TemplateParameters(Input):
    package_name: str = Field(
        default="batch_app", pattern=r"^batch_[a-z][a-z0-9_]{0,39}$", max_length=46
    )


class GenerationInput(Input):
    template_id: Literal["python-batch:1.0.0"] = "python-batch:1.0.0"
    binding_id: UUID
    expected_binding_version: int = Field(ge=1, strict=True)
    parameters: TemplateParameters = Field(default_factory=TemplateParameters)


class RevisionInput(Input):
    generation_id: UUID
    binding_id: UUID
    expected_binding_version: int = Field(ge=1, strict=True)


class ValidationInput(Input):
    scope: Literal["offline"]


class TemplateResponse(Input):
    id: str
    content_digest: str
    parameter_schema: dict
    active: bool


class GenerationResponse(Record):
    operation_id: UUID
    application_id: UUID
    template_id: str
    parameters: dict
    binding_snapshot: dict
    artifact_digest: str | None


class RevisionResponse(Record):
    application_id: UUID
    generation_id: UUID
    source_kind: Literal["generated"]
    artifact_digest: str
    template_id: str
    template_digest: str
    binding_id: UUID
    binding_snapshot: dict
    config_snapshot: dict
    config_digest: str
    requested_by: int


class ValidationResponse(Record):
    revision_id: UUID
    operation_id: UUID
    scope: Literal["offline"]
    validator_version: str
    result: Literal["passed", "failed"]
    report_digest: str
    observed_at: datetime
