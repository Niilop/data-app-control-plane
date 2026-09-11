"""Strict, bounded inputs and explicit registry responses."""

import re
from datetime import datetime, timezone
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

Name = Annotated[str, Field(min_length=1, max_length=200, pattern=r"\S")]
Role = Literal["viewer", "developer", "approver", "operator"]


def validate_repository_url(value: str) -> str:
    if not re.fullmatch(
        r"https://github\.com/[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}",
        value,
    ):
        raise ValueError(
            "Use an HTTPS github.com owner/repository URL without credentials, query or fragment"
        )
    if value.rsplit("/", 1)[1] in {".", "..", ".git"}:
        raise ValueError("Invalid repository name")
    return value.removesuffix(".git")


def validate_bundle_root(value: str) -> str:
    if value == ".":
        return value
    if not all(
        re.fullmatch(r"[A-Za-z0-9_.-]+", part) and part not in {".", ".."}
        for part in value.split("/")
    ):
        raise ValueError(
            "Use a relative bundle path without traversal or empty segments"
        )
    return value


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TeamCreate(Input):
    name: Annotated[str, Field(min_length=1, max_length=100, pattern=r"\S")]


class MemberCreate(Input):
    user_id: int = Field(gt=0)


class RoleCreate(Input):
    user_id: int | None = Field(default=None, gt=0)
    team_id: UUID | None = None
    role: Role

    @model_validator(mode="after")
    def one_subject(self) -> "RoleCreate":
        if (self.user_id is None) == (self.team_id is None):
            raise ValueError("Exactly one user or team subject is required")
        return self


class ApplicationCreate(Input):
    slug: str = Field(
        min_length=1, max_length=63, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    name: Name
    description: str = Field(default="", max_length=4000)
    owning_team_id: UUID
    owner_user_id: int = Field(gt=0)
    data_owner_user_id: int = Field(gt=0)
    repository_url: str = Field(max_length=500)
    bundle_root: str = Field(default=".", max_length=500)
    _repository = field_validator("repository_url")(validate_repository_url)
    _bundle = field_validator("bundle_root")(validate_bundle_root)


class ApplicationUpdate(Input):
    expected_version: int = Field(ge=1)
    name: Name | None = None
    description: str | None = Field(default=None, max_length=4000)
    owning_team_id: UUID | None = None
    owner_user_id: int | None = Field(default=None, gt=0)
    data_owner_user_id: int | None = Field(default=None, gt=0)
    repository_url: str | None = Field(default=None, max_length=500)
    bundle_root: str | None = Field(default=None, max_length=500)

    @field_validator("repository_url", "bundle_root")
    @classmethod
    def validate_source(cls, value: str | None, info: object) -> str | None:
        # Nulls are rejected by the model validator along with other patch fields.
        if value is None:
            return value
        return (
            validate_repository_url(value)
            if getattr(info, "field_name") == "repository_url"
            else validate_bundle_root(value)
        )

    @model_validator(mode="after")
    def nonempty_patch(self) -> "ApplicationUpdate":
        fields = self.model_fields_set - {"expected_version"}
        if not fields or any(getattr(self, field) is None for field in fields):
            raise ValueError("Provide at least one non-null metadata field")
        return self


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created(self, value: datetime) -> str:
        return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()


class TeamResponse(Record):
    name: str


class MemberResponse(Record):
    team_id: UUID
    user_id: int


class RoleResponse(Record):
    application_id: UUID
    user_id: int | None
    team_id: UUID | None
    role: Role


class ApplicationResponse(Record):
    slug: str
    name: str
    description: str
    owning_team_id: UUID
    owner_user_id: int
    data_owner_user_id: int
    repository_url: str
    bundle_root: str
    repository_verified_at: datetime | None
    lifecycle: Literal["registered", "active", "archived"]
    created_by: int
    version: int
    updated_at: datetime

    @field_serializer("updated_at")
    def serialize_updated(self, value: datetime) -> str:
        return value.replace(tzinfo=value.tzinfo or timezone.utc).isoformat()


class AuditResponse(Record):
    actor_user_id: int | None
    actor_kind: str
    action: str
    target_type: str
    target_id: str
    outcome: str
    request_id: str
    details: dict


class ApplicationCapabilities(BaseModel):
    """Current UI affordances; never a substitute for mutation authorization."""

    edit_metadata: bool
    manage_access: bool
    manage_bindings: bool
    operate: bool


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None
