"""Add versioned environments and unique application bindings."""

import sqlalchemy as sa
from alembic import op

revision = "006_environment_bindings"
down_revision = "005_owned_applications"
branch_labels = None
depends_on = None


def versioned_identity() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "environments",
        *versioned_identity(),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("workspace_ref", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("allowed_executor", sa.String(30), nullable=False),
        sa.Column("allow_self_approval", sa.Boolean(), nullable=False),
        sa.Column("allowed_bundle_targets", sa.JSON(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_environment_version"),
        sa.CheckConstraint(
            "allowed_executor = 'simulated'", name="ck_environment_executor"
        ),
    )
    op.create_table(
        "environment_bindings",
        *versioned_identity(),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id"),
            nullable=False,
        ),
        sa.Column(
            "environment_id",
            sa.Uuid(),
            sa.ForeignKey("environments.id"),
            nullable=False,
        ),
        sa.Column("bundle_target", sa.String(63), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "application_id", "environment_id", name="uq_application_environment"
        ),
        sa.CheckConstraint("version >= 1", name="ck_binding_version"),
    )
    for column in ("application_id", "environment_id"):
        op.create_index(
            f"ix_environment_bindings_{column}", "environment_bindings", [column]
        )


def downgrade() -> None:
    op.drop_table("environment_bindings")
    op.drop_table("environments")
