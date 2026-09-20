"""Persisted generation provenance and append-only preparation records."""

from datetime import datetime
from uuid import UUID

from core.database import Base
from models.platform import Identity
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column


class TemplateVersion(Base):
    __tablename__ = "template_versions"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    content_digest: Mapped[str] = mapped_column(String(64))
    parameter_schema: Mapped[dict] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(default=True)


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint("size >= 0 AND size <= 2000000", name="ck_artifact_size"),
    )
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    size: Mapped[int]
    media_type: Mapped[str] = mapped_column(String(80))


class Generation(Identity, Base):
    __tablename__ = "generations"
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("operations.id"), unique=True)
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    template_id: Mapped[str] = mapped_column(ForeignKey("template_versions.id"))
    parameters: Mapped[dict] = mapped_column(JSON)
    binding_snapshot: Mapped[dict] = mapped_column(JSON)
    artifact_digest: Mapped[str | None] = mapped_column(ForeignKey("artifacts.digest"))


class DeploymentRevision(Identity, Base):
    __tablename__ = "deployment_revisions"
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    generation_id: Mapped[UUID] = mapped_column(ForeignKey("generations.id"))
    source_kind: Mapped[str] = mapped_column(String(30), default="generated")
    artifact_digest: Mapped[str] = mapped_column(ForeignKey("artifacts.digest"))
    template_id: Mapped[str] = mapped_column(ForeignKey("template_versions.id"))
    template_digest: Mapped[str] = mapped_column(String(64))
    binding_id: Mapped[UUID] = mapped_column(ForeignKey("environment_bindings.id"))
    binding_snapshot: Mapped[dict] = mapped_column(JSON)
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    config_digest: Mapped[str] = mapped_column(String(64))
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))


class ValidationResult(Identity, Base):
    __tablename__ = "validation_results"
    __table_args__ = (
        CheckConstraint(
            "scope = 'offline' AND result IN ('passed','failed')",
            name="ck_validation_scope_result",
        ),
    )
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("deployment_revisions.id"), index=True
    )
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("operations.id"), unique=True)
    scope: Mapped[str] = mapped_column(String(30), default="offline")
    validator_version: Mapped[str] = mapped_column(String(50), default="static-v1")
    result: Mapped[str] = mapped_column(String(30))
    report_digest: Mapped[str] = mapped_column(ForeignKey("artifacts.digest"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def immutable(mapper: object, connection: object, target: object) -> None:
    raise ValueError("Preparation record is immutable")


for model in (Artifact, DeploymentRevision, ValidationResult):
    event.listen(model, "before_update", immutable)
    event.listen(model, "before_delete", immutable)


@event.listens_for(TemplateVersion, "before_update")
def template_immutable(
    mapper: object, connection: object, target: TemplateVersion
) -> None:
    if any(
        inspect(target).attrs[name].history.has_changes()
        for name in ("id", "content_digest", "parameter_schema")
    ):
        raise ValueError("Template content is immutable")
