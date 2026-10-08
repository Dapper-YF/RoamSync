"""Link recovery planning runs to deterministic disruption facts.

Revision ID: 20260915_0024
Revises: 20260915_0023
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260915_0024"
down_revision = "20260915_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("planning_runs", sa.Column("disruption_event_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_planning_runs_disruption_event", "planning_runs", "trip_disruption_events", ["disruption_event_id"], ["id"], ondelete="SET NULL")
    op.create_index(
        "uq_planning_runs_active_recovery", "planning_runs", ["disruption_event_id"], unique=True,
        postgresql_where=sa.text("disruption_event_id IS NOT NULL AND status IN ('queued', 'researching', 'awaiting_clarification', 'planning', 'validating', 'awaiting_confirmation')"),
    )
    op.add_column("trip_disruption_events", sa.Column("resolution_plan_revision_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("trip_disruption_events", sa.Column("resolution_planning_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_disruption_resolution_revision", "trip_disruption_events", "plan_revisions", ["resolution_plan_revision_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_disruption_resolution_run", "trip_disruption_events", "planning_runs", ["resolution_planning_run_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_disruption_resolution_run", "trip_disruption_events", type_="foreignkey")
    op.drop_constraint("fk_disruption_resolution_revision", "trip_disruption_events", type_="foreignkey")
    op.drop_column("trip_disruption_events", "resolution_planning_run_id")
    op.drop_column("trip_disruption_events", "resolution_plan_revision_id")
    op.drop_index("uq_planning_runs_active_recovery", table_name="planning_runs")
    op.drop_constraint("fk_planning_runs_disruption_event", "planning_runs", type_="foreignkey")
    op.drop_column("planning_runs", "disruption_event_id")
