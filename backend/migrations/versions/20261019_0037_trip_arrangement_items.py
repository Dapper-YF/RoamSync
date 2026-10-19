"""Finite Trip-owned choices and reserved free intervals, no second timetable."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261019_0037"
down_revision = "20261018_0036"
branch_labels = depends_on = None


def upgrade():
    op.create_table("trip_arrangement_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("identity_key", sa.String(250), nullable=False),
        sa.Column("source_ref", sa.String(200), nullable=False),
        sa.Column("decision_ref", sa.String(200), nullable=False),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("place_candidates.id", ondelete="RESTRICT")),
        sa.Column("day_date", sa.Date()), sa.Column("start_time", sa.Time()), sa.Column("end_time", sa.Time()),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("activities.id", ondelete="SET NULL")),
        sa.UniqueConstraint("trip_id", "identity_key", name="uq_arrangement_trip_identity"),
        sa.UniqueConstraint("activity_id", name="uq_arrangement_activity"),
        sa.CheckConstraint("kind IN ('selected','optional','free_window','cancelled')", name="ck_arrangement_kind"),
        sa.CheckConstraint("length(trim(source_ref)) > 0 AND length(trim(label)) > 0", name="ck_arrangement_source"),
        sa.CheckConstraint("activity_id IS NULL OR kind='selected'", name="ck_arrangement_link"),
        sa.CheckConstraint("(kind='free_window' AND day_date IS NOT NULL AND start_time IS NOT NULL AND end_time IS NOT NULL AND start_time < end_time AND place_id IS NULL AND activity_id IS NULL) OR (kind!='free_window' AND start_time IS NULL AND end_time IS NULL)", name="ck_arrangement_precision"))
    op.create_index("ix_trip_arrangement_items_trip_id", "trip_arrangement_items", ["trip_id"])


def downgrade():
    # Explicit developer migration only; application code never drops decisions.
    op.drop_table("trip_arrangement_items")
