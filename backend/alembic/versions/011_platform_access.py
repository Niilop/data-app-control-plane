"""Own-access requests; preserve existing roles, accounts and application history."""

import sqlalchemy as sa
from alembic import op

revision = "011_platform_access"
down_revision = "010_simulated_job_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "access_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id"),
            nullable=False,
        ),
        sa.Column(
            "requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("requested_role", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decision_reason", sa.String(2000), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "requested_role IN ('viewer','developer','approver','operator')",
            name="ck_access_request_role",
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled')",
            name="ck_access_request_status",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND decided_by IS NULL AND decided_at IS NULL "
            "AND decision_reason IS NULL) OR (status <> 'pending' "
            "AND decided_by IS NOT NULL AND decided_at IS NOT NULL "
            "AND decision_reason IS NOT NULL)",
            name="ck_access_request_decision",
        ),
    )
    op.create_index(
        "ix_access_requests_application_id", "access_requests", ["application_id"]
    )
    op.create_index(
        "ix_access_requests_requested_by", "access_requests", ["requested_by"]
    )
    op.create_index(
        "uq_pending_access_request",
        "access_requests",
        ["application_id", "requested_by", "requested_role"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM access_requests)")):
        raise RuntimeError("Cannot downgrade a database with access request history")
    op.drop_table("access_requests")
