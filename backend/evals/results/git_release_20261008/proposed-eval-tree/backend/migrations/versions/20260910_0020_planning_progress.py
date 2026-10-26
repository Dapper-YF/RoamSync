"""Expose actual planning stages and worker heartbeat."""
from alembic import op
import sqlalchemy as sa

revision = "20260910_0020"
down_revision = "20260909_0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("planning_runs", sa.Column("progress", sa.JSON(), nullable=True))
    op.add_column("planning_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("planning_runs", "heartbeat_at")
    op.drop_column("planning_runs", "progress")
