"""persist pending planning interrupt for web clients

Revision ID: 20260902_0013
Revises: 20260902_0012
"""

from alembic import op
import sqlalchemy as sa


revision = "20260902_0013"
down_revision = "20260902_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("planning_runs", sa.Column("pending_interrupt", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("planning_runs", "pending_interrupt")
