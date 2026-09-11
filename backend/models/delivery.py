"""Template versions, immutable artifacts, revisions and validation results.

Artifact content and revision snapshots are immutable: no service updates these
rows after creation, and no endpoint exposes a change. New input creates a new
record. None of these fields hold credentials or credential values.
"""

from datetime import datetime
from uuid import UUID

from core.database import Base
from models.platform import Identity, utcnow
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column


class TemplateVersion(Identity, Base):
    """A reviewed on-disk template version, pinned by its content digest."""

    __tablename__ = "template_versions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_template_version"),)
    name: Mapped[str] = mapped_column(String(63))
    version: Mapped[str] = mapped_column(String(30))
    content_digest: Mapped[str] = mapped_column(String(64))
    parameter_schema: Mapped[dict] = mapped_column(JSON)
    tool_versions: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(default=True)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class Artifact(Identity, Base):
    """Immutable stored content, addressed by digest and scoped to one application."""

    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("application_id", "digest", name="uq_artifact_application"),
        CheckConstraint("size_bytes > 0", name="ck_artifact_size"),
        CheckConstraint(
            "kind IN ('generated_bundle','validation_report')", name="ck_artifact_kind"
        ),
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    digest: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(200))
    size_bytes: Mapped[int]
    media_type: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(30))
    provenance: Mapped[dict] = mapped_column(JSON)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    operation_id: Mapped[UUID | None] = mapped_column(ForeignKey("operations.id"))


class DeploymentRevision(Identity, Base):
    """An immutable snapshot of source, template, binding policy and configuration."""

    __tablename__ = "deployment_revisions"
    __table_args__ = (
        CheckConstraint(
            "source_kind = 'generated_artifact'", name="ck_revision_source_kind"
        ),
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    source_kind: Mapped[str] = mapped_column(String(30), default="generated_artifact")
    artifact_id: Mapped[UUID] = mapped_column(ForeignKey("artifacts.id"))
    artifact_digest: Mapped[str] = mapped_column(String(64))
    template_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("template_versions.id")
    )
    binding_id: Mapped[UUID] = mapped_column(ForeignKey("environment_bindings.id"))
    binding_version: Mapped[int]
    bundle_target: Mapped[str] = mapped_column(String(63))
    binding_snapshot: Mapped[dict] = mapped_column(JSON)
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    config_digest: Mapped[str] = mapped_column(String(64))
    scope_digest: Mapped[str] = mapped_column(String(64), index=True)
    execution_mode: Mapped[str] = mapped_column(String(30), default="simulated")
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[str] = mapped_column(String(36))


class ValidationResult(Identity, Base):
    """An append-only validation observation; offline scope is never workspace scope."""

    __tablename__ = "validation_results"
    __table_args__ = (
        CheckConstraint("scope = 'offline'", name="ck_validation_scope"),
        CheckConstraint("result IN ('passed','failed')", name="ck_validation_result"),
    )
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("deployment_revisions.id"), index=True
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("operations.id"), unique=True)
    scope: Mapped[str] = mapped_column(String(20), default="offline")
    validator: Mapped[str] = mapped_column(String(50))
    validator_version: Mapped[str] = mapped_column(String(30))
    tool_versions: Mapped[dict] = mapped_column(JSON)
    result: Mapped[str | None] = mapped_column(String(20))
    check_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    report_artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("artifacts.id"))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
