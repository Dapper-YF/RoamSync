"""Keep actionable validation failures on persisted planning runs."""

from alembic import op
import sqlalchemy as sa

revision = "20260908_0017"
down_revision = "20260907_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("planning_runs", sa.Column("error_details", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("planning_runs", "error_details")
