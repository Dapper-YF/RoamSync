"""Add persisted route legs and route cache.

Revision ID: 20260901_0003
Revises: 20260901_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260901_0003"
down_revision: str | None = "20260901_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "day_plans",
        sa.Column("route_mode", sa.String(length=12), nullable=False, server_default="walk"),
    )
    op.alter_column("day_plans", "route_mode", server_default=None)
    op.create_table(
        "route_legs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "day_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("day_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "from_activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("activities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("distance_meters", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("is_estimated", sa.Boolean(), nullable=False),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("day_plan_id", "position", name="uq_route_legs_day_position"),
        sa.CheckConstraint("position >= 0", name="ck_route_legs_position_nonnegative"),
        sa.CheckConstraint("distance_meters >= 0", name="ck_route_legs_distance_nonnegative"),
        sa.CheckConstraint("duration_minutes >= 0", name="ck_route_legs_duration_nonnegative"),
        sa.CheckConstraint(
            "mode IN ('walk', 'transit', 'driving')",
            name="ck_route_legs_mode_allowed",
        ),
    )
    op.create_table(
        "route_cache",
        sa.Column("cache_key", sa.String(length=64), primary_key=True),
        sa.Column("mode", sa.String(length=12), nullable=False),
        sa.Column("distance_meters", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("is_estimated", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("route_cache")
    op.drop_table("route_legs")
    op.drop_column("day_plans", "route_mode")
