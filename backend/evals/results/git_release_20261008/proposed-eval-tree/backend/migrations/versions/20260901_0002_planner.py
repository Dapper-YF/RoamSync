"""Add persisted trip planning models.

Revision ID: 20260901_0002
Revises: 20260831_0001
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260901_0002"
down_revision: str | None = "20260831_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trips",
        sa.Column("destination", sa.String(length=120), server_default="", nullable=False),
    )
    op.add_column(
        "trips",
        sa.Column("accommodation", sa.String(length=240), server_default="", nullable=False),
    )
    op.alter_column("trips", "destination", server_default=None)
    op.alter_column("trips", "accommodation", server_default=None)

    op.create_table(
        "day_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("label", sa.String(length=40), nullable=False),
        sa.Column("theme", sa.String(length=160), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_day_plans_position_nonnegative"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "date", name="uq_day_plans_trip_date"),
        sa.UniqueConstraint("trip_id", "position", name="uq_day_plans_trip_position"),
    )
    op.create_table(
        "source_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("queried_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.String(length=10), nullable=False),
        sa.CheckConstraint("confidence IN ('high', 'medium', 'low')", name="ck_source_records_confidence_allowed"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "place_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("neighborhood", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("suggested_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_fen", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.Numeric(precision=2, scale=1), nullable=False),
        sa.Column("tags", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("category IN ('sight', 'food', 'culture', 'nature', 'shopping')", name="ck_place_candidates_category_allowed"),
        sa.CheckConstraint("suggested_duration_minutes > 0", name="ck_place_candidates_duration_positive"),
        sa.CheckConstraint("estimated_cost_fen >= 0", name="ck_place_candidates_cost_nonnegative"),
        sa.CheckConstraint("rating >= 0 AND rating <= 5", name="ck_place_candidates_rating"),
        sa.ForeignKeyConstraint(["source_record_id"], ["source_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "slug", name="uq_place_candidates_trip_slug"),
    )
    op.create_table(
        "activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day_plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("place_candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheduled_time", sa.Time(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_fen", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_activities_position_nonnegative"),
        sa.CheckConstraint("duration_minutes > 0", name="ck_activities_duration_positive"),
        sa.CheckConstraint("estimated_cost_fen >= 0", name="ck_activities_cost_nonnegative"),
        sa.CheckConstraint("status IN ('planned', 'active', 'completed', 'skipped')", name="ck_activities_status_allowed"),
        sa.ForeignKeyConstraint(["day_plan_id"], ["day_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["place_candidate_id"], ["place_candidates.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("day_plan_id", "place_candidate_id", name="uq_activities_day_place"),
        sa.UniqueConstraint("day_plan_id", "position", name="uq_activities_day_position"),
    )


def downgrade() -> None:
    op.drop_table("activities")
    op.drop_table("place_candidates")
    op.drop_table("source_records")
    op.drop_table("day_plans")
    op.drop_column("trips", "accommodation")
    op.drop_column("trips", "destination")
