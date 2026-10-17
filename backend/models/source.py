"""GitHub source snapshots and append-only CI observations."""

from datetime import datetime
from uuid import UUID

from core.database import Base
from models.delivery import immutable
from models.platform import Identity
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    event,
    inspect,
)
from sqlalchemy.orm import Mapped, mapped_column


class SourceCapture(Identity, Base):
    __tablename__ = "source_captures"
    __table_args__ = (
        CheckConstraint(
            "(commit_sha IS NULL AND repository_id IS NULL) OR "
            "(commit_sha IS NOT NULL AND repository_id IS NOT NULL)",
            name="ck_source_resolution",
        ),
        CheckConstraint(
            "artifact_digest IS NULL OR (commit_sha IS NOT NULL AND captured_at IS NOT NULL)",
            name="ck_source_completion",
        ),
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("operations.id"), unique=True)
    repository_url: Mapped[str] = mapped_column(String(500))
    bundle_root: Mapped[str] = mapped_column(String(500))
    requested_ref: Mapped[str] = mapped_column(String(200))
    binding_snapshot: Mapped[dict] = mapped_column(JSON)
    template_id: Mapped[str] = mapped_column(ForeignKey("template_versions.id"))
    template_digest: Mapped[str] = mapped_column(String(64))
    repository_id: Mapped[int | None] = mapped_column(BigInteger)
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    artifact_digest: Mapped[str | None] = mapped_column(ForeignKey("artifacts.digest"))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CIRun(Identity, Base):
    __tablename__ = "ci_runs"
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id"), index=True
    )
    source_capture_id: Mapped[UUID] = mapped_column(
        ForeignKey("source_captures.id"), index=True
    )
    operation_id: Mapped[UUID] = mapped_column(ForeignKey("operations.id"), index=True)
    commit_sha: Mapped[str] = mapped_column(String(40))
    run_id: Mapped[int] = mapped_column(BigInteger)
    run_attempt: Mapped[int]
    workflow_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(30))
    conclusion: Mapped[str | None] = mapped_column(String(30))
    event: Mapped[str] = mapped_column(String(50))
    url: Mapped[str] = mapped_column(String(500))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@event.listens_for(SourceCapture, "before_update")
def capture_immutable(
    mapper: object, connection: object, target: SourceCapture
) -> None:
    for attr in inspect(target).attrs:
        if not attr.history.has_changes():
            continue
        if attr.key not in {
            "commit_sha",
            "repository_id",
            "artifact_digest",
            "captured_at",
        }:
            raise ValueError("Source capture inputs are immutable")
        if attr.history.deleted and attr.history.deleted[0] is not None:
            raise ValueError("Captured source is immutable")


event.listen(SourceCapture, "before_delete", immutable)
for action in ("before_update", "before_delete"):
    event.listen(CIRun, action, immutable)
