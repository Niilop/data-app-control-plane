"""Add background_jobs table for async task tracking.

Revision ID: 004_add_background_jobs
Revises: 003_add_chat_threads
Create Date: 2026-03-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '004_add_background_jobs'
down_revision = '003_add_chat_threads'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'background_jobs',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('job_type', sa.String(100), nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', name='jobstatus'), nullable=False, server_default='pending'),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_background_jobs_id', 'background_jobs', ['id'])
    op.create_index('ix_background_jobs_user_id', 'background_jobs', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_background_jobs_user_id', table_name='background_jobs')
    op.drop_index('ix_background_jobs_id', table_name='background_jobs')
    op.drop_table('background_jobs')
    op.execute("DROP TYPE IF EXISTS jobstatus")
