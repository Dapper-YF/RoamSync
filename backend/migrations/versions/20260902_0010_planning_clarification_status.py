"""add planning clarification status

Revision ID: 20260902_0010
Revises: 20260902_0009
"""

from alembic import op


revision = "20260902_0010"
down_revision = "20260902_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_planning_runs_status", "planning_runs", type_="check")
    op.create_check_constraint(
        "ck_planning_runs_status",
        "planning_runs",
        "status IN ('queued', 'researching', 'awaiting_clarification', 'planning', "
        "'validating', 'awaiting_confirmation', 'accepted', 'rejected', 'failed', 'cancelled')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE planning_runs SET status = 'researching' "
        "WHERE status = 'awaiting_clarification'"
    )
    op.drop_constraint("ck_planning_runs_status", "planning_runs", type_="check")
    op.create_check_constraint(
        "ck_planning_runs_status",
        "planning_runs",
        "status IN ('queued', 'researching', 'planning', 'validating', "
        "'awaiting_confirmation', 'accepted', 'rejected', 'failed', 'cancelled')",
    )
