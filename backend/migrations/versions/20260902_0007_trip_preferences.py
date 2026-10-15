"""add structured trip preferences

Revision ID: 20260902_0007
Revises: 20260901_0006
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260902_0007"
down_revision = "20260901_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trip_preferences",
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pace", sa.String(16), nullable=False, server_default="balanced"),
        sa.Column("interest_categories", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "transport_modes",
            sa.JSON(),
            nullable=False,
            server_default='["walk", "transit"]',
        ),
        sa.Column("daily_start_time", sa.Time(), nullable=False, server_default="09:00:00"),
        sa.Column("daily_end_time", sa.Time(), nullable=False, server_default="21:00:00"),
        sa.Column("meal_preferences", sa.String(500), nullable=False, server_default=""),
        sa.Column("avoid_categories", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("max_walking_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("free_text_requirements", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "pace IN ('relaxed', 'balanced', 'intensive')",
            name="ck_trip_preferences_pace_allowed",
        ),
        sa.CheckConstraint(
            "daily_end_time > daily_start_time",
            name="ck_trip_preferences_daily_window",
        ),
        sa.CheckConstraint(
            "max_walking_minutes > 0 AND max_walking_minutes <= 480",
            name="ck_trip_preferences_max_walking_minutes",
        ),
        sa.CheckConstraint("version > 0", name="ck_trip_preferences_version_positive"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("trip_id"),
    )
    op.execute(
        """
        INSERT INTO trip_preferences (trip_id)
        SELECT id FROM trips
        ON CONFLICT (trip_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("trip_preferences")
