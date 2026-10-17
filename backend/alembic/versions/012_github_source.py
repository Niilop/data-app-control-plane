"""Immutable GitHub captures and CI observations, without changing old history."""

import sqlalchemy as sa
from alembic import op

revision = "012_github_source"
down_revision = "011_platform_access"
branch_labels = None
depends_on = None

OLD_HANDLERS = "(kind IN ('queue_probe','deploy_simulated','run_simulated') AND execution_mode = 'simulated') OR (kind IN ('generate_bundle','validate_offline') AND execution_mode = 'offline')"


def upgrade() -> None:
    op.create_table(
        "source_captures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id"),
            nullable=False,
        ),
        sa.Column(
            "operation_id",
            sa.Uuid(),
            sa.ForeignKey("operations.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("repository_url", sa.String(500), nullable=False),
        sa.Column("bundle_root", sa.String(500), nullable=False),
        sa.Column("requested_ref", sa.String(200), nullable=False),
        sa.Column("binding_snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "template_id",
            sa.String(80),
            sa.ForeignKey("template_versions.id"),
            nullable=False,
        ),
        sa.Column("template_digest", sa.String(64), nullable=False),
        sa.Column("repository_id", sa.BigInteger(), nullable=True),
        sa.Column("commit_sha", sa.String(40), nullable=True),
        sa.Column(
            "artifact_digest",
            sa.String(64),
            sa.ForeignKey("artifacts.digest"),
            nullable=True,
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(commit_sha IS NULL AND repository_id IS NULL) OR (commit_sha IS NOT NULL AND repository_id IS NOT NULL)",
            name="ck_source_resolution",
        ),
        sa.CheckConstraint(
            "artifact_digest IS NULL OR (commit_sha IS NOT NULL AND captured_at IS NOT NULL)",
            name="ck_source_completion",
        ),
    )
    op.create_index(
        "ix_source_captures_application_id", "source_captures", ["application_id"]
    )
    op.create_table(
        "ci_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id"),
            nullable=False,
        ),
        sa.Column(
            "source_capture_id",
            sa.Uuid(),
            sa.ForeignKey("source_captures.id"),
            nullable=False,
        ),
        sa.Column(
            "operation_id", sa.Uuid(), sa.ForeignKey("operations.id"), nullable=False
        ),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("run_attempt", sa.Integer(), nullable=False),
        sa.Column("workflow_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("conclusion", sa.String(30), nullable=True),
        sa.Column("event", sa.String(50), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )
    for field in ("application_id", "source_capture_id", "operation_id"):
        op.create_index(f"ix_ci_runs_{field}", "ci_runs", [field])
    op.add_column(
        "deployment_revisions", sa.Column("source_capture_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_revision_capture",
        "deployment_revisions",
        "source_captures",
        ["source_capture_id"],
        ["id"],
    )
    op.alter_column("deployment_revisions", "generation_id", nullable=True)
    op.create_check_constraint(
        "ck_revision_source",
        "deployment_revisions",
        "(source_kind = 'generated' AND generation_id IS NOT NULL AND source_capture_id IS NULL) OR (source_kind = 'github' AND generation_id IS NULL AND source_capture_id IS NOT NULL)",
    )
    op.drop_constraint("ck_operation_handler", "operations", type_="check")
    op.create_check_constraint(
        "ck_operation_handler",
        "operations",
        OLD_HANDLERS
        + " OR (kind IN ('capture_github','refresh_github_ci') AND execution_mode = 'github_read')",
    )
    op.execute("""CREATE FUNCTION guard_source_capture() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Source capture is immutable'; END IF;
        IF (to_jsonb(NEW) - ARRAY['commit_sha','repository_id','artifact_digest','captured_at'])
          IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['commit_sha','repository_id','artifact_digest','captured_at'])
          OR (OLD.commit_sha IS NOT NULL AND NEW.commit_sha IS DISTINCT FROM OLD.commit_sha)
          OR (OLD.repository_id IS NOT NULL AND NEW.repository_id IS DISTINCT FROM OLD.repository_id)
          OR (OLD.artifact_digest IS NOT NULL AND NEW.artifact_digest IS DISTINCT FROM OLD.artifact_digest)
          OR (OLD.captured_at IS NOT NULL AND NEW.captured_at IS DISTINCT FROM OLD.captured_at)
        THEN RAISE EXCEPTION 'Source capture is immutable'; END IF;
        RETURN NEW;
      END; $$""")
    op.execute(
        "CREATE TRIGGER immutable_source BEFORE UPDATE OR DELETE ON source_captures FOR EACH ROW EXECUTE FUNCTION guard_source_capture()"
    )
    op.execute(
        "CREATE TRIGGER immutable_ci BEFORE UPDATE OR DELETE ON ci_runs FOR EACH ROW EXECUTE FUNCTION reject_preparation_mutation()"
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM source_captures) OR EXISTS(SELECT 1 FROM operations WHERE execution_mode = 'github_read')"
        )
    ):
        raise RuntimeError("Cannot downgrade a database with GitHub source history")
    op.drop_constraint("ck_revision_source", "deployment_revisions", type_="check")
    op.drop_constraint(
        "fk_revision_capture", "deployment_revisions", type_="foreignkey"
    )
    op.drop_column("deployment_revisions", "source_capture_id")
    op.alter_column("deployment_revisions", "generation_id", nullable=False)
    op.drop_table("ci_runs")
    op.drop_table("source_captures")
    op.execute("DROP FUNCTION guard_source_capture()")
    op.drop_constraint("ck_operation_handler", "operations", type_="check")
    op.create_check_constraint("ck_operation_handler", "operations", OLD_HANDLERS)
