"""Separate simulated job history; preserve existing deployment evidence."""

import sqlalchemy as sa
from alembic import op

revision = "010_simulated_job_runs"
down_revision = "009_simulated_deployments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id"),
            nullable=False,
        ),
        sa.Column(
            "deployment_id", sa.Uuid(), sa.ForeignKey("deployments.id"), nullable=False
        ),
        sa.Column(
            "operation_id",
            sa.Uuid(),
            sa.ForeignKey("operations.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("resource_key", sa.String(50), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("scenario", sa.String(20), nullable=False),
        sa.Column("execution_mode", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("provider_run_id", sa.String(100), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("execution_mode = 'simulated'", name="ck_job_run_mode"),
        sa.CheckConstraint(
            "resource_key = 'synthetic_job'", name="ck_job_run_resource"
        ),
        sa.CheckConstraint(
            "scenario IN ('success','failure')", name="ck_job_run_scenario"
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled','unknown')",
            name="ck_job_run_status",
        ),
        sa.CheckConstraint("provider_run_id IS NULL", name="ck_job_run_no_provider"),
    )
    op.create_index("ix_job_runs_application_id", "job_runs", ["application_id"])
    op.create_index("ix_job_runs_deployment_id", "job_runs", ["deployment_id"])
    op.drop_constraint("ck_operation_handler", "operations", type_="check")
    op.create_check_constraint(
        "ck_operation_handler",
        "operations",
        "(kind IN ('queue_probe','deploy_simulated','run_simulated') AND execution_mode = 'simulated') OR (kind IN ('generate_bundle','validate_offline') AND execution_mode = 'offline')",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM job_runs) OR EXISTS(SELECT 1 FROM operations WHERE kind = 'run_simulated')"
        )
    ):
        raise RuntimeError("Cannot downgrade a database with job run history")
    op.drop_table("job_runs")
    op.drop_constraint("ck_operation_handler", "operations", type_="check")
    op.create_check_constraint(
        "ck_operation_handler",
        "operations",
        "(kind IN ('queue_probe','deploy_simulated') AND execution_mode = 'simulated') OR (kind IN ('generate_bundle','validate_offline') AND execution_mode = 'offline')",
    )
