"""Persist runtime navigation sessions separately from replaceable RouteLeg rows.

Revision ID: 20260915_0022
Revises: 20260914_0021
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260915_0022"
down_revision = "20260914_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "navigation_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trip_execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trip_executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("formal_route_leg_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("itinerary_version", sa.Integer(), nullable=False),
        sa.Column("travel_mode", sa.String(length=12), nullable=False),
        sa.Column("coordinate_system", sa.String(length=16), nullable=False, server_default="gcj02"),
        sa.Column("origin_longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("origin_latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("destination_longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("destination_latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("planned_departure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planned_arrival_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_eta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remaining_distance_meters", sa.Integer(), nullable=True),
        sa.Column("current_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("progress_ratio", sa.Numeric(5, 4), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("provider_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("route_path", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("route_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_location_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_location_longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("last_location_latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("last_location_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('created', 'active', 'rerouting', 'arrived', 'completed', 'failed', 'cancelled', 'superseded')", name="ck_navigation_sessions_status_allowed"),
        sa.CheckConstraint("itinerary_version > 0", name="ck_navigation_sessions_itinerary_version_positive"),
        sa.CheckConstraint("route_revision >= 0", name="ck_navigation_sessions_route_revision_nonnegative"),
        sa.CheckConstraint("state_version > 0", name="ck_navigation_sessions_state_version_positive"),
        sa.CheckConstraint("last_location_sequence >= 0", name="ck_navigation_sessions_location_sequence_nonnegative"),
        sa.CheckConstraint("progress_ratio IS NULL OR (progress_ratio >= 0 AND progress_ratio <= 1)", name="ck_navigation_sessions_progress_ratio_range"),
    )
    op.create_index("uq_navigation_sessions_execution_live", "navigation_sessions", ["trip_execution_id"], unique=True,
                    postgresql_where=sa.text("status IN ('active', 'rerouting')"))
    op.create_index("ix_navigation_sessions_trip_created", "navigation_sessions", ["trip_id", "created_at"])


def downgrade() -> None:
    op.drop_table("navigation_sessions")
