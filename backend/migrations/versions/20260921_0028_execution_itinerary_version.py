"""fence execution projections to their formal itinerary

Revision ID: 20260921_0028
Revises: 20260921_0027
"""
from alembic import op
import sqlalchemy as sa

revision = "20260921_0028"
down_revision = "20260921_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trip_executions", sa.Column("itinerary_version", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column("trip_executions", "itinerary_version", server_default=None)


def downgrade() -> None:
    op.drop_column("trip_executions", "itinerary_version")
