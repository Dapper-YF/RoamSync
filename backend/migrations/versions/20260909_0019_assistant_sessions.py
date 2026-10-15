"""Persistent cross-page assistant conversations and tool confirmations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260909_0019"
down_revision = "20260909_0018"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("assistant_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=True),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("pending_action", sa.JSON(), nullable=True),
        sa.Column("applied_actions", sa.JSON(), nullable=False),
        sa.Column("latest_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("planning_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_assistant_sessions_trip_id", "assistant_sessions", ["trip_id"])


def downgrade():
    op.drop_table("assistant_sessions")
