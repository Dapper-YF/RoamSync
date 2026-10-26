"""Persist navigation observations and deterministic detector state.

Revision ID: 20260916_0025
Revises: 20260915_0024
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260916_0025"
down_revision = "20260915_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("navigation_sessions", sa.Column("last_location_accuracy_meters", sa.Numeric(8, 2), nullable=True))
    op.add_column("navigation_sessions", sa.Column("remaining_duration_seconds", sa.Integer(), nullable=True))
    op.add_column("navigation_sessions", sa.Column("navigation_status", sa.String(16), nullable=True))
    op.add_column("navigation_sessions", sa.Column("observation_source", sa.String(16), nullable=True))
    op.add_column("navigation_sessions", sa.Column("last_observation_fingerprint", sa.String(64), nullable=True))
    op.create_check_constraint(
        "ck_navigation_sessions_accuracy_nonnegative",
        "navigation_sessions",
        "last_location_accuracy_meters IS NULL OR last_location_accuracy_meters >= 0",
    )
    op.create_check_constraint(
        "ck_navigation_sessions_remaining_duration_nonnegative",
        "navigation_sessions",
        "remaining_duration_seconds IS NULL OR remaining_duration_seconds >= 0",
    )
    op.create_check_constraint(
        "ck_navigation_sessions_navigation_status",
        "navigation_sessions",
        "navigation_status IS NULL OR navigation_status IN ('navigating', 'rerouting', 'paused', 'arrived')",
    )
    op.create_check_constraint(
        "ck_navigation_sessions_observation_source",
        "navigation_sessions",
        "observation_source IS NULL OR observation_source IN ('simulation', 'real_gps')",
    )

    op.create_table(
        "navigation_detection_states",
        sa.Column(
            "navigation_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("navigation_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("itinerary_version", sa.Integer(), nullable=False),
        sa.Column("last_processed_observation_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_risk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_risk_state", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("minimum_downstream_slack_minutes", sa.Integer(), nullable=True),
        sa.Column("first_impacted_activity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_risk_transition_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_escalation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("itinerary_version > 0", name="ck_navigation_detection_version_positive"),
        sa.CheckConstraint("last_processed_observation_sequence >= 0", name="ck_navigation_detection_sequence_nonnegative"),
        sa.CheckConstraint("consecutive_risk_count >= 0", name="ck_navigation_detection_count_nonnegative"),
        sa.CheckConstraint(
            "current_risk_state IN ('normal', 'warning', 'critical', 'infeasible')",
            name="ck_navigation_detection_risk_state",
        ),
    )
    op.execute(
        """
        INSERT INTO navigation_detection_states (
            navigation_session_id, itinerary_version, last_processed_observation_sequence
        )
        SELECT id, itinerary_version, last_location_sequence
        FROM navigation_sessions
        """
    )


def downgrade() -> None:
    op.drop_table("navigation_detection_states")
    op.drop_constraint("ck_navigation_sessions_observation_source", "navigation_sessions", type_="check")
    op.drop_constraint("ck_navigation_sessions_navigation_status", "navigation_sessions", type_="check")
    op.drop_constraint("ck_navigation_sessions_remaining_duration_nonnegative", "navigation_sessions", type_="check")
    op.drop_constraint("ck_navigation_sessions_accuracy_nonnegative", "navigation_sessions", type_="check")
    op.drop_column("navigation_sessions", "last_observation_fingerprint")
    op.drop_column("navigation_sessions", "observation_source")
    op.drop_column("navigation_sessions", "navigation_status")
    op.drop_column("navigation_sessions", "remaining_duration_seconds")
    op.drop_column("navigation_sessions", "last_location_accuracy_meters")
