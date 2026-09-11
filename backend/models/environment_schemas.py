"""Simulated environment policy and a closed, versioned binding configuration."""

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from models.platform_schemas import Input, Record
from pydantic import (
    Field,
    StrictBool,
    field_serializer,
    field_validator,
    model_validator,
)

Target = Annotated[
    str, Field(min_length=1, max_length=63, pattern=r"^[a-z][a-z0-9_-]*$")
]
WorkspaceRef = Annotated[
    str, Field(max_length=100, pattern=r"^simulated://[a-z][a-z0-9-]{0,62}$")
]
Targets = Annotated[list[Target], Field(min_length=1, max_length=20)]


class SafeBindingConfig(Input):
    schema_version: Literal[1] = 1
    synthetic_row_count: int = Field(default=100, ge=1, le=10000, strict=True)
    max_runtime_seconds: int = Field(default=300, ge=1, le=3600, strict=True)

    @field_validator("schema_version", mode="before")
    @classmethod
    def strict_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Configuration schema version must be integer 1")
        return value


class EnvironmentCreate(Input):
    name: Annotated[str, Field(min_length=1, max_length=100, pattern=r"\S")]
    workspace_ref: WorkspaceRef
    allowed_executor: Literal["simulated"]
    enabled: StrictBool = True
    allow_self_approval: StrictBool = False
    allowed_bundle_targets: Targets

    @field_validator("allowed_bundle_targets")
    @classmethod
    def unique_targets(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Bundle targets must be unique")
        return sorted(value)


class EnvironmentUpdate(Input):
    expected_version: int = Field(ge=1)
    name: Annotated[str | None, Field(min_length=1, max_length=100, pattern=r"\S")] = (
        None
    )
    workspace_ref: WorkspaceRef | None = None
    allowed_executor: Literal["simulated"] | None = None
    enabled: StrictBool | None = None
    allow_self_approval: StrictBool | None = None
    allowed_bundle_targets: Targets | None = None

    @model_validator(mode="after")
    def patch_fields(self) -> "EnvironmentUpdate":
        fields = self.model_fields_set - {"expected_version"}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError("Provide at least one non-null environment field")
        if self.allowed_bundle_targets is not None:
            self.allowed_bundle_targets = EnvironmentCreate.unique_targets(
                self.allowed_bundle_targets
            )
        return self


class VersionedRecord(Record):
    version: int
    updated_at: datetime

    @field_serializer("updated_at")
    def serialize_updated(self, value: datetime) -> str:
        return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()


class EnvironmentResponse(VersionedRecord):
    name: str
    workspace_ref: str
    enabled: bool
    allowed_executor: Literal["simulated"]
    allow_self_approval: bool
    allowed_bundle_targets: list[str]
    execution_mode: Literal["simulated"] = "simulated"


class BindingCreate(Input):
    environment_id: UUID
    bundle_target: Target
    config: SafeBindingConfig = Field(default_factory=SafeBindingConfig)


class BindingUpdate(Input):
    expected_version: int = Field(ge=1)
    bundle_target: Target | None = None
    config: SafeBindingConfig | None = None

    @model_validator(mode="after")
    def patch_fields(self) -> "BindingUpdate":
        fields = self.model_fields_set - {"expected_version"}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError("Provide at least one non-null binding field")
        return self


class BindingResponse(VersionedRecord):
    application_id: UUID
    environment_id: UUID
    bundle_target: str
    config: SafeBindingConfig
    environment: EnvironmentResponse
    execution_mode: Literal["simulated"] = "simulated"
    usable: bool
