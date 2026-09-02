"""add candidate route evidence

Revision ID: 20260902_0009
Revises: 20260902_0008
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260902_0009"
down_revision = "20260902_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "candidate_route_legs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day_date", sa.Date(), nullable=False),
        sa.Column("from_activity_ref", sa.String(80), nullable=False),
        sa.Column("to_activity_ref", sa.String(80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(12), nullable=False),
        sa.Column("distance_meters", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("is_estimated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name="ck_candidate_route_legs_position_nonnegative"
        ),
        sa.CheckConstraint(
            "distance_meters >= 0", name="ck_candidate_route_legs_distance_nonnegative"
        ),
        sa.CheckConstraint(
            "duration_minutes >= 0", name="ck_candidate_route_legs_duration_nonnegative"
        ),
        sa.CheckConstraint(
            "mode IN ('walk', 'transit', 'driving')",
            name="ck_candidate_route_legs_mode_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["plan_revision_id"], ["plan_revisions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_revision_id", "day_date", "position",
            name="uq_candidate_route_legs_revision_day_position",
        ),
    )
    op.create_index(
        "ix_candidate_route_legs_revision_day",
        "candidate_route_legs",
        ["plan_revision_id", "day_date", "position"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_candidate_route_legs_revision_day", table_name="candidate_route_legs"
    )
    op.drop_table("candidate_route_legs")
