"""persist plan revision rejection feedback

Revision ID: 20260924_0033
Revises: 20260922_0032
"""

from alembic import op
import sqlalchemy as sa


revision = "20260924_0033"
down_revision = "20260922_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plan_revisions", sa.Column("rejection_reason_code", sa.String(length=40), nullable=True))
    op.add_column("plan_revisions", sa.Column("rejection_reason_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("plan_revisions", "rejection_reason_text")
    op.drop_column("plan_revisions", "rejection_reason_code")
