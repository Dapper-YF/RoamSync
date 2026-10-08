"""persist minimal general replanning trigger metadata

Revision ID: 20260921_0029
Revises: 20260921_0028
"""
from alembic import op
import sqlalchemy as sa

revision = "20260921_0029"
down_revision = "20260921_0028"
branch_labels = None
depends_on = None

ACTIVE = "status IN ('queued','researching','awaiting_clarification','planning','validating','awaiting_confirmation')"

def upgrade() -> None:
    op.add_column("planning_runs", sa.Column("trigger_type", sa.String(length=32), nullable=True))
    op.add_column("planning_runs", sa.Column("trigger_key", sa.String(length=200), nullable=True))
    op.add_column("planning_runs", sa.Column("trigger_snapshot", sa.JSON(), nullable=True))
    op.create_index("uq_planning_runs_active_trigger", "planning_runs", ["trip_id", "trigger_key"], unique=True, postgresql_where=sa.text("trigger_key IS NOT NULL AND " + ACTIVE))

def downgrade() -> None:
    op.drop_index("uq_planning_runs_active_trigger", table_name="planning_runs")
    op.drop_column("planning_runs", "trigger_snapshot")
    op.drop_column("planning_runs", "trigger_key")
    op.drop_column("planning_runs", "trigger_type")
