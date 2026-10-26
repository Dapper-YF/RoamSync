"""add planning run and candidate revision boundaries

Revision ID: 20260902_0008
Revises: 20260902_0007
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260902_0008"
down_revision = "20260902_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planning_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("user_request", sa.Text(), nullable=False, server_default=""),
        sa.Column("base_trip_version", sa.Integer(), nullable=False),
        sa.Column("model_provider", sa.String(40), nullable=True),
        sa.Column("model_name", sa.String(120), nullable=True),
        sa.Column("token_usage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("run_type IN ('initial_plan', 'replan')", name="ck_planning_runs_type"),
        sa.CheckConstraint("status IN ('queued', 'researching', 'planning', 'validating', 'awaiting_confirmation', 'accepted', 'rejected', 'failed', 'cancelled')", name="ck_planning_runs_status"),
        sa.CheckConstraint("base_trip_version > 0", name="ck_planning_runs_base_version"),
        sa.CheckConstraint("token_usage >= 0", name="ck_planning_runs_token_usage"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_planning_runs_trip_created", "planning_runs", ["trip_id", "created_at"])
    op.create_table(
        "plan_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("planning_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("before_snapshot", sa.JSON(), nullable=False),
        sa.Column("proposed_snapshot", sa.JSON(), nullable=False),
        sa.Column("difference_summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("validation_result", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("source_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("revision_number > 0", name="ck_plan_revisions_number"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'rejected', 'superseded')", name="ck_plan_revisions_status"),
        sa.ForeignKeyConstraint(["planning_run_id"], ["planning_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("planning_run_id", "revision_number", name="uq_plan_revisions_run_number"),
    )
    op.create_index("ix_plan_revisions_trip_created", "plan_revisions", ["trip_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_plan_revisions_trip_created", table_name="plan_revisions")
    op.drop_table("plan_revisions")
    op.drop_index("ix_planning_runs_trip_created", table_name="planning_runs")
    op.drop_table("planning_runs")
