"""serialize active automatic recovery per formal trip version

Revision ID: 20260921_0030
Revises: 20260921_0029
"""
from alembic import op
import sqlalchemy as sa

revision = "20260921_0030"
down_revision = "20260921_0029"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_index(
        "uq_planning_runs_active_automatic_version", "planning_runs",
        ["trip_id", "base_trip_version"], unique=True,
        postgresql_where=sa.text("trigger_type IN ('navigation_disruption','experience_impact') AND status IN ('queued','researching','awaiting_clarification','planning','validating','awaiting_confirmation')"),
    )

def downgrade() -> None:
    op.drop_index("uq_planning_runs_active_automatic_version", table_name="planning_runs")
