"""make experience rejection dedup queryable

Revision ID: 20260921_0031
Revises: 20260921_0030
"""
from alembic import op
import sqlalchemy as sa

revision = "20260921_0031"
down_revision = "20260921_0030"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("planning_runs", sa.Column("trigger_fingerprint", sa.String(length=64), nullable=True))
    op.create_index("ix_planning_runs_experience_fingerprint", "planning_runs", ["trip_id", "trigger_type", "trigger_key", "trigger_fingerprint"])

def downgrade() -> None:
    op.drop_index("ix_planning_runs_experience_fingerprint", table_name="planning_runs")
    op.drop_column("planning_runs", "trigger_fingerprint")
