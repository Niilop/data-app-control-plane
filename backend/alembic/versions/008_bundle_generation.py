"""Add template versions, artifacts, revisions and offline validation results.

Migrations 001-007 are unchanged. The only edit to an existing table replaces the
operation handler check constraint so the queue accepts the two new local kinds;
existing rows remain valid because `queue_probe`/`simulated` is still allowed.
"""

import sqlalchemy as sa
from alembic import op

revision = "008_bundle_generation"
down_revision = "007_durable_operations"
branch_labels = None
depends_on = None

OLD_HANDLER = "kind = 'queue_probe' AND execution_mode = 'simulated'"
NEW_HANDLER = (
    "(kind = 'queue_probe' AND execution_mode = 'simulated')"
    " OR (kind IN ('bundle_generation','offline_validation')"
    " AND execution_mode = 'local')"
)


def upgrade() -> None:
    op.create_table(
        "template_versions",
        sa.Column("name", sa.String(length=63), nullable=False),
        sa.Column("version", sa.String(length=30), nullable=False),
        sa.Column("content_digest", sa.String(length=64), nullable=False),
        sa.Column("parameter_schema", sa.JSON(), nullable=False),
        sa.Column("tool_versions", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_template_version"),
    )
    op.create_table(
        "artifacts",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=200), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("size_bytes > 0", name="ck_artifact_size"),
        sa.CheckConstraint(
            "kind IN ('generated_bundle','validation_report')", name="ck_artifact_kind"
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["operation_id"], ["operations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", "digest", name="uq_artifact_application"),
    )
    op.create_index(
        op.f("ix_artifacts_application_id"),
        "artifacts",
        ["application_id"],
        unique=False,
    )
    op.create_index(op.f("ix_artifacts_digest"), "artifacts", ["digest"], unique=False)
    op.create_table(
        "deployment_revisions",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("source_kind", sa.String(length=30), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_digest", sa.String(length=64), nullable=False),
        sa.Column("template_version_id", sa.Uuid(), nullable=False),
        sa.Column("binding_id", sa.Uuid(), nullable=False),
        sa.Column("binding_version", sa.Integer(), nullable=False),
        sa.Column("bundle_target", sa.String(length=63), nullable=False),
        sa.Column("binding_snapshot", sa.JSON(), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("config_digest", sa.String(length=64), nullable=False),
        sa.Column("scope_digest", sa.String(length=64), nullable=False),
        sa.Column("execution_mode", sa.String(length=30), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_kind = 'generated_artifact'", name="ck_revision_source_kind"
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"]),
        sa.ForeignKeyConstraint(["binding_id"], ["environment_bindings.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["template_version_id"], ["template_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_deployment_revisions_application_id"),
        "deployment_revisions",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_deployment_revisions_scope_digest"),
        "deployment_revisions",
        ["scope_digest"],
        unique=False,
    )
    op.create_table(
        "validation_results",
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("validator", sa.String(length=50), nullable=False),
        sa.Column("validator_version", sa.String(length=30), nullable=False),
        sa.Column("tool_versions", sa.JSON(), nullable=False),
        sa.Column("result", sa.String(length=20), nullable=True),
        sa.Column("check_summary", sa.JSON(), nullable=False),
        sa.Column("report_artifact_id", sa.Uuid(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("scope = 'offline'", name="ck_validation_scope"),
        sa.CheckConstraint(
            "result IN ('passed','failed')", name="ck_validation_result"
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["operation_id"], ["operations.id"]),
        sa.ForeignKeyConstraint(["report_artifact_id"], ["artifacts.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["revision_id"], ["deployment_revisions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id"),
    )
    op.create_index(
        op.f("ix_validation_results_application_id"),
        "validation_results",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_validation_results_revision_id"),
        "validation_results",
        ["revision_id"],
        unique=False,
    )
    with op.batch_alter_table("operations") as batch:
        batch.drop_constraint("ck_operation_handler", type_="check")
        batch.create_check_constraint("ck_operation_handler", NEW_HANDLER)


def downgrade() -> None:
    # Existing local operations would violate the narrower constraint; a caller
    # downgrading a populated database must resolve them first.
    with op.batch_alter_table("operations") as batch:
        batch.drop_constraint("ck_operation_handler", type_="check")
        batch.create_check_constraint("ck_operation_handler", OLD_HANDLER)
    op.drop_table("validation_results")
    op.drop_table("deployment_revisions")
    op.drop_table("artifacts")
    op.drop_table("template_versions")
