"""Independent source-bound intentions, never a second activity timetable."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20261022_0038"
down_revision = "20261019_0037"
branch_labels = depends_on = None


def upgrade():
    op.create_table("saved_intentions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scope_session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_session_id", UUID(as_uuid=True), sa.ForeignKey("assistant_sessions.id", ondelete="SET NULL")),
        sa.Column("source_message_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_index", sa.Integer(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(40), nullable=False),
        sa.Column("place_text", sa.String(160), nullable=False),
        sa.Column("city_text", sa.String(120)),
        sa.Column("intended_date", sa.Date()),
        sa.Column("time_period", sa.String(20)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("linked_arrangement_item_id", UUID(as_uuid=True), sa.ForeignKey("trip_arrangement_items.id", ondelete="SET NULL")),
        sa.UniqueConstraint("scope_session_id", "source_message_id", "source_index", name="uq_intention_source"),
        sa.CheckConstraint("status IN ('active','cancelled','transferred')", name="ck_intention_status"))
    op.create_index("ix_saved_intentions_scope_session_id", "saved_intentions", ["scope_session_id"])


def downgrade():
    op.drop_table("saved_intentions")
