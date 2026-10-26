"""add trip management and accommodation metadata

Revision ID: 20260901_0005
Revises: 20260901_0004
"""

from alembic import op
import sqlalchemy as sa

revision = "20260901_0005"
down_revision = "20260901_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("accommodation_address", sa.String(300), nullable=False, server_default=""))
    op.add_column("trips", sa.Column("accommodation_district", sa.String(120), nullable=False, server_default=""))
    op.add_column("trips", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("trips", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("trips", "version")
    op.drop_column("trips", "archived_at")
    op.drop_column("trips", "accommodation_district")
    op.drop_column("trips", "accommodation_address")
