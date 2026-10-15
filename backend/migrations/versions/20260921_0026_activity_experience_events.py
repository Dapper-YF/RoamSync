"""add idempotent activity experience event facts

Revision ID: 20260921_0026
Revises: 20260916_0025
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260921_0026"
down_revision = "20260916_0025"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("travel_events", sa.Column("client_action_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("uq_travel_events_execution_action", "travel_events", ["trip_execution_id", "client_action_id"], unique=True, postgresql_where=sa.text("client_action_id IS NOT NULL"))
    op.drop_constraint("ck_travel_events_type_allowed", "travel_events", type_="check")
    op.create_check_constraint("ck_travel_events_type_allowed", "travel_events", "event_type IN ('trip_started','arrived','activity_started','completed','skipped','paused','resumed','trip_finished','delay','temporary_closure','weather_change','fatigue','budget_change','user_change','user_extend_stay','user_leave_early')")

def downgrade() -> None:
    op.drop_constraint("ck_travel_events_type_allowed", "travel_events", type_="check")
    op.create_check_constraint("ck_travel_events_type_allowed", "travel_events", "event_type IN ('trip_started','arrived','activity_started','completed','skipped','paused','resumed','trip_finished','delay','temporary_closure','weather_change','fatigue','budget_change','user_change')")
    op.drop_index("uq_travel_events_execution_action", table_name="travel_events")
    op.drop_column("travel_events", "client_action_id")
