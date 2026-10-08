"""index activity experience fact aggregation

Revision ID: 20260921_0027
Revises: 20260921_0026
"""
from alembic import op

revision = "20260921_0027"
down_revision = "20260921_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_travel_events_activity_type", "travel_events", ["activity_execution_id", "event_type"])


def downgrade() -> None:
    op.drop_index("ix_travel_events_activity_type", table_name="travel_events")
