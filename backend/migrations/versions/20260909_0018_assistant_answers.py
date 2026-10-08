"""Persist read-only assistant answers separately from plan revisions."""
from alembic import op
import sqlalchemy as sa

revision = "20260909_0018"
down_revision = "20260908_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("planning_runs", sa.Column("response_text", sa.Text(), nullable=True))
    op.drop_constraint("ck_planning_runs_status", "planning_runs", type_="check")
    op.create_check_constraint("ck_planning_runs_status", "planning_runs", "status IN ('queued', 'researching', 'awaiting_clarification', 'planning', 'validating', 'awaiting_confirmation', 'accepted', 'rejected', 'failed', 'cancelled', 'answered')")


def downgrade():
    # Preserve historical answers rather than deleting user conversation data.
    op.execute("UPDATE planning_runs SET status = 'cancelled' WHERE status = 'answered'")
    op.drop_constraint("ck_planning_runs_status", "planning_runs", type_="check")
    op.create_check_constraint("ck_planning_runs_status", "planning_runs", "status IN ('queued', 'researching', 'awaiting_clarification', 'planning', 'validating', 'awaiting_confirmation', 'accepted', 'rejected', 'failed', 'cancelled')")
    op.drop_column("planning_runs", "response_text")
