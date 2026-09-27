"""Append exact approvals and simulated deployments after merged preparation."""

import sqlalchemy as sa
from alembic import op

revision = "009_simulated_deployments"
down_revision = "008_prepared_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "revision_id",
            sa.Uuid(),
            sa.ForeignKey("deployment_revisions.id"),
            nullable=False,
        ),
        sa.Column(
            "validation_id",
            sa.Uuid(),
            sa.ForeignKey("validation_results.id"),
            nullable=False,
        ),
        sa.Column("scope_digest", sa.String(64), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column(
            "approver_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("policy_version", sa.String(30), nullable=False),
        sa.Column("self_approval_acknowledged", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approved','rejected')", name="ck_approval_decision"
        ),
    )
    op.create_index("ix_approvals_revision_id", "approvals", ["revision_id"])
    op.execute(
        "CREATE TRIGGER immutable_approval BEFORE UPDATE OR DELETE ON approvals FOR EACH ROW EXECUTE FUNCTION reject_preparation_mutation()"
    )
    op.create_table(
        "deployments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "application_id",
            sa.Uuid(),
            sa.ForeignKey("applications.id"),
            nullable=False,
        ),
        sa.Column(
            "binding_id",
            sa.Uuid(),
            sa.ForeignKey("environment_bindings.id"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            sa.Uuid(),
            sa.ForeignKey("deployment_revisions.id"),
            nullable=False,
        ),
        sa.Column(
            "approval_id", sa.Uuid(), sa.ForeignKey("approvals.id"), nullable=False
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
        sa.Column("executor", sa.String(30), nullable=False),
        sa.Column("execution_mode", sa.String(30), nullable=False),
        sa.Column("scenario", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("resources", sa.JSON(), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "execution_mode = 'simulated' AND executor = 'simulated'",
            name="ck_deployment_mode",
        ),
        sa.CheckConstraint(
            "status IN ('queued','deploying','succeeded','failed','unknown','cancelled')",
            name="ck_deployment_status",
        ),
        sa.CheckConstraint(
            "scenario IN ('success','partial_failure')", name="ck_deployment_scenario"
        ),
    )
    op.create_index("ix_deployments_application_id", "deployments", ["application_id"])
    op.drop_constraint("ck_operation_handler", "operations", type_="check")
    op.create_check_constraint(
        "ck_operation_handler",
        "operations",
        "(kind IN ('queue_probe','deploy_simulated') AND execution_mode = 'simulated') OR (kind IN ('generate_bundle','validate_offline') AND execution_mode = 'offline')",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM approvals) OR EXISTS(SELECT 1 FROM operations WHERE kind = 'deploy_simulated')"
        )
    ):
        raise RuntimeError(
            "Cannot downgrade a database with approval/deployment history"
        )
    op.drop_table("deployments")
    op.drop_table("approvals")
    op.drop_constraint("ck_operation_handler", "operations", type_="check")
    op.create_check_constraint(
        "ck_operation_handler",
        "operations",
        "(kind = 'queue_probe' AND execution_mode = 'simulated') OR (kind IN ('generate_bundle','validate_offline') AND execution_mode = 'offline')",
    )
