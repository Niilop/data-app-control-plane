"""Platform registry, separate from historical pipelines and jobs."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from core.database import Base
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Identity:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Team(Identity, Base):
    __tablename__ = "teams"
    name: Mapped[str] = mapped_column(String(100), unique=True)


class TeamMembership(Identity, Base):
    __tablename__ = "team_memberships"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class Application(Identity, Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_application_version"),
        CheckConstraint(
            "lifecycle IN ('registered', 'active', 'archived')",
            name="ck_application_lifecycle",
        ),
    )
    slug: Mapped[str] = mapped_column(String(63), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(4000), default="")
    owning_team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id"), index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    data_owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    repository_url: Mapped[str] = mapped_column(String(500))
    bundle_root: Mapped[str] = mapped_column(String(500), default=".")
    repository_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    lifecycle: Mapped[str] = mapped_column(String(20), default="registered")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class ApplicationRole(Identity, Base):
    __tablename__ = "application_roles"
    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL AND team_id IS NULL) OR (user_id IS NULL AND team_id IS NOT NULL)",
            name="ck_role_subject",
        ),
        CheckConstraint(
            "role IN ('viewer', 'developer', 'approver', 'operator')",
            name="ck_application_role",
        ),
        UniqueConstraint(
            "application_id", "user_id", "role", name="uq_application_user_role"
        ),
        UniqueConstraint(
            "application_id", "team_id", "role", name="uq_application_team_role"
        ),
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    team_id: Mapped[UUID | None] = mapped_column(ForeignKey("teams.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    actor_kind: Mapped[str] = mapped_column(String(30), default="user")
    action: Mapped[str] = mapped_column(String(100))
    target_type: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    application_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    outcome: Mapped[str] = mapped_column(String(20), default="success")
    request_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class Environment(Identity, Base):
    __tablename__ = "environments"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_environment_version"),
        CheckConstraint(
            "allowed_executor = 'simulated'", name="ck_environment_executor"
        ),
    )
    name: Mapped[str] = mapped_column(String(100), unique=True)
    workspace_ref: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(default=True)
    allowed_executor: Mapped[str] = mapped_column(String(30))
    allow_self_approval: Mapped[bool] = mapped_column(default=False)
    allowed_bundle_targets: Mapped[list[str]] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class EnvironmentBinding(Identity, Base):
    __tablename__ = "environment_bindings"
    __table_args__ = (
        UniqueConstraint(
            "application_id", "environment_id", name="uq_application_environment"
        ),
        CheckConstraint("version >= 1", name="ck_binding_version"),
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    environment_id: Mapped[UUID] = mapped_column(
        ForeignKey("environments.id"), index=True
    )
    bundle_target: Mapped[str] = mapped_column(String(63))
    config: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
