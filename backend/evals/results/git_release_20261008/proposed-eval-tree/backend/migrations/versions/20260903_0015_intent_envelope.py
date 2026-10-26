"""persist grounded intent context on planning runs

Revision ID: 20260903_0015
Revises: 20260903_0014
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260903_0015"
down_revision = "20260903_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "planning_runs",
        sa.Column(
            "entry_point",
            sa.String(24),
            nullable=False,
            server_default="trip_planner",
        ),
    )
    op.add_column(
        "planning_runs",
        sa.Column("selected_day_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "planning_runs",
        sa.Column("selected_activity_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "planning_runs",
        sa.Column("intent_resolution", sa.JSON(), nullable=True),
    )
    op.create_foreign_key(
        "fk_planning_runs_selected_day",
        "planning_runs",
        "day_plans",
        ["selected_day_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_planning_runs_selected_activity",
        "planning_runs",
        "activities",
        ["selected_activity_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("planning_runs", "entry_point", server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "fk_planning_runs_selected_activity", "planning_runs", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_planning_runs_selected_day", "planning_runs", type_="foreignkey"
    )
    op.drop_column("planning_runs", "intent_resolution")
    op.drop_column("planning_runs", "selected_activity_id")
    op.drop_column("planning_runs", "selected_day_id")
    op.drop_column("planning_runs", "entry_point")
