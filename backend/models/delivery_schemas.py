"""Closed generation/revision inputs and explicit delivery responses.

Client input is deliberately narrow. Slug, bundle target and configuration bounds
come from the registry and the binding, not from the request, so a caller cannot
inject a target, path, command or credential into a generated project.
"""

import keyword
import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from models.environment_schemas import SafeBindingConfig
from models.platform_schemas import Input, Record
from pydantic import Field, field_serializer, field_validator

PACKAGE_NAME = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
OUTPUT_SEGMENT = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
Digest = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


def validate_package_name(value: str) -> str:
    if not PACKAGE_NAME.fullmatch(value):
        raise ValueError(
            "Use a lowercase Python package name such as customer_analytics"
        )
    if keyword.iskeyword(value) or keyword.issoftkeyword(value):
        raise ValueError("Package name must not be a Python keyword")
    if value in {"tests", "src", "resources", "main"}:
        raise ValueError("Package name is reserved by the generated project layout")
    return value


def validate_output_path(value: str) -> str:
    """A relative POSIX path inside the project: no traversal, root or device."""
    segments = value.split("/")
    if len(segments) > 4 or not all(
        OUTPUT_SEGMENT.fullmatch(segment) for segment in segments
    ):
        raise ValueError(
            "Use a relative path of lowercase segments, such as output/synthetic.csv"
        )
    if not segments[-1].endswith(".csv"):
        raise ValueError("The synthetic output file must be a .csv file")
    return value


class GenerationInput(Input):
    """Payload schema 1 for the bundle generation operation."""

    schema_version: int = Field(default=1, ge=1, le=1, strict=True)
    template_name: str = Field(min_length=1, max_length=63, pattern=r"^[a-z0-9-]+$")
    template_version: str = Field(
        min_length=1, max_length=30, pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$"
    )
    binding_id: UUID
    package_name: str = Field(max_length=40)
    synthetic_output_path: str = Field(default="output/synthetic.csv", max_length=120)
    _package = field_validator("package_name")(validate_package_name)
    _output = field_validator("synthetic_output_path")(validate_output_path)


class ValidationInput(Input):
    """Offline scope is the only supported scope; workspace validation does not exist."""

    scope: Literal["offline"] = "offline"


class RevisionCreate(Input):
    artifact_digest: str = Digest
    binding_id: UUID
    expected_binding_version: int | None = Field(default=None, ge=1)
    config: SafeBindingConfig | None = None


class TemplateParameter(Input):
    name: str
    kind: str | None = None
    label: str | None = None
    description: str
    example: str | None = None
    source: str | None = None


class TemplateResponse(Input):
    name: str
    version: str
    title: str
    summary: str
    active: bool
    content_digest: str
    payload_version: int
    tool_versions: dict
    supplied_parameters: list[TemplateParameter]
    derived_parameters: list[TemplateParameter]
    produces: list[str]


class ArtifactResponse(Record):
    application_id: UUID
    digest: str
    size_bytes: int
    media_type: str
    kind: Literal["generated_bundle", "validation_report"]
    provenance: dict
    created_by: int
    operation_id: UUID | None


class ValidationResponse(Record):
    revision_id: UUID
    operation_id: UUID
    scope: Literal["offline"]
    validator: str
    validator_version: str
    tool_versions: dict
    result: Literal["passed", "failed"] | None
    check_summary: dict
    report_artifact_id: UUID | None
    observed_at: datetime | None
    requested_by: int

    @field_serializer("observed_at")
    def timestamp(self, value: datetime | None) -> str | None:
        return (
            value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()
            if value
            else None
        )


class RevisionResponse(Record):
    application_id: UUID
    source_kind: Literal["generated_artifact"]
    artifact_id: UUID
    artifact_digest: str
    template_version_id: UUID
    binding_id: UUID
    binding_version: int
    bundle_target: str
    binding_snapshot: dict
    config_snapshot: dict
    config_digest: str
    scope_digest: str
    execution_mode: Literal["simulated"]
    requested_by: int
