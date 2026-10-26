"""add persistent trip execution state

Revision ID: 20260903_0014
Revises: 20260902_0013
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260903_0014"
down_revision = "20260902_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trip_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("current_date", sa.Date(), nullable=False),
        sa.Column("current_day_plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("day_plans.id", ondelete="SET NULL")),
        sa.Column("current_activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("activities.id", ondelete="SET NULL")),
        sa.Column("actual_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_ended_at", sa.DateTime(timezone=True)),
        sa.Column("paused_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('in_progress', 'paused', 'completed')", name="ck_trip_executions_status_allowed"),
        sa.UniqueConstraint("trip_id", name="uq_trip_executions_trip"),
    )
    op.create_table(
        "activity_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trip_execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trip_executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("actual_arrived_at", sa.DateTime(timezone=True)),
        sa.Column("actual_started_at", sa.DateTime(timezone=True)),
        sa.Column("actual_ended_at", sa.DateTime(timezone=True)),
        sa.Column("delay_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending', 'arrived', 'in_progress', 'completed', 'skipped')", name="ck_activity_executions_status_allowed"),
        sa.CheckConstraint("delay_minutes >= 0", name="ck_activity_executions_delay_nonnegative"),
        sa.UniqueConstraint("trip_execution_id", "activity_id", name="uq_activity_executions_trip_activity"),
    )
    op.create_index("ix_activity_executions_trip_status", "activity_executions", ["trip_execution_id", "status"])
    op.create_table(
        "travel_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trip_execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trip_executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("activity_executions.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.CheckConstraint("event_type IN ('trip_started', 'arrived', 'activity_started', 'completed', 'skipped', 'paused', 'resumed', 'trip_finished', 'delay', 'temporary_closure', 'weather_change', 'fatigue', 'budget_change', 'user_change')", name="ck_travel_events_type_allowed"),
    )
    op.create_index("ix_travel_events_execution_occurred", "travel_events", ["trip_execution_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_travel_events_execution_occurred", table_name="travel_events")
    op.drop_table("travel_events")
    op.drop_index("ix_activity_executions_trip_status", table_name="activity_executions")
    op.drop_table("activity_executions")
    op.drop_table("trip_executions")
