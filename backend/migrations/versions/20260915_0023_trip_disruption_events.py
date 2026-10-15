"""Persist de-duplicated deterministic trip disruptions.

Revision ID: 20260915_0023
Revises: 20260915_0022
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260915_0023"
down_revision = "20260915_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trip_disruption_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trip_execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trip_executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("navigation_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("navigation_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("itinerary_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("impacted_identity", sa.String(120), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("impact_snapshot", sa.JSON(), nullable=False),
        sa.Column("dedup_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("event_type IN ('missed_time_window', 'itinerary_infeasible')", name="ck_trip_disruptions_type"),
        sa.CheckConstraint("status IN ('active', 'resolved', 'dismissed')", name="ck_trip_disruptions_status"),
    )
    op.create_index("uq_trip_disruptions_active_dedup", "trip_disruption_events", ["dedup_key"], unique=True, postgresql_where=sa.text("status = 'active'"))
    op.create_index("ix_trip_disruptions_trip_detected", "trip_disruption_events", ["trip_id", "detected_at"])


def downgrade() -> None:
    op.drop_table("trip_disruption_events")
