"""Owned application registry; preserve all historical tables and users."""

import sqlalchemy as sa
from alembic import op

revision = "005_owned_applications"
down_revision = "004_add_background_jobs"
branch_labels = None
depends_on = None


def identity() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_table(
        "teams",
        *identity(),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
    )
    op.create_table(
        "team_memberships",
        *identity(),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
    )
    op.create_table(
        "applications",
        *identity(),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(4000), nullable=False),
        sa.Column(
            "owning_team_id", sa.Uuid(), sa.ForeignKey("teams.id"), nullable=False
        ),
        sa.Column(
            "owner_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "data_owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("repository_url", sa.String(500), nullable=False),
        sa.Column("bundle_root", sa.String(500), nullable=False),
        sa.Column("repository_verified_at", sa.DateTime(timezone=True)),
        sa.Column("lifecycle", sa.String(20), nullable=False),
        sa.Column(
            "created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_application_version"),
        sa.CheckConstraint(
            "lifecycle IN ('registered', 'active', 'archived')",
            name="ck_application_lifecycle",
        ),
    )
    op.create_table(
        "application_roles",
        *identity(),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("team_id", sa.Uuid(), sa.ForeignKey("teams.id")),
        sa.Column("role", sa.String(20), nullable=False),
        sa.CheckConstraint(
            "(user_id IS NOT NULL AND team_id IS NULL) OR (user_id IS NULL AND team_id IS NOT NULL)",
            name="ck_role_subject",
        ),
        sa.CheckConstraint(
            "role IN ('viewer', 'developer', 'approver', 'operator')",
            name="ck_application_role",
        ),
        sa.UniqueConstraint(
            "application_id", "user_id", "role", name="uq_application_user_role"
        ),
        sa.UniqueConstraint(
            "application_id", "team_id", "role", name="uq_application_team_role"
        ),
    )
    op.create_table(
        "audit_events",
        *identity(),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("actor_kind", sa.String(30), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("application_id", sa.Uuid(), sa.ForeignKey("applications.id")),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
    )
    for table, columns in {
        "team_memberships": ("team_id", "user_id"),
        "applications": ("owning_team_id", "owner_user_id", "data_owner_user_id"),
        "application_roles": ("application_id", "user_id", "team_id"),
        "audit_events": ("target_id", "application_id"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    for table in (
        "audit_events",
        "application_roles",
        "applications",
        "team_memberships",
        "teams",
    ):
        op.drop_table(table)
    op.drop_column("users", "is_platform_admin")
    op.drop_column("users", "is_active")
