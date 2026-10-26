"""add multi-city trip metadata

Revision ID: 20260901_0004
Revises: 20260901_0003
"""

from alembic import op
import sqlalchemy as sa

revision = "20260901_0004"
down_revision = "20260901_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("destination_adcode", sa.String(12), nullable=False, server_default=""))
    op.add_column("trips", sa.Column("destination_citycode", sa.String(12), nullable=False, server_default=""))
    op.add_column("trips", sa.Column("center_longitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("trips", sa.Column("center_latitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("trips", sa.Column("accommodation_poi_id", sa.String(80), nullable=False, server_default=""))
    op.add_column("trips", sa.Column("accommodation_longitude", sa.Numeric(9, 6), nullable=True))
    op.add_column("trips", sa.Column("accommodation_latitude", sa.Numeric(9, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "accommodation_latitude")
    op.drop_column("trips", "accommodation_longitude")
    op.drop_column("trips", "accommodation_poi_id")
    op.drop_column("trips", "center_latitude")
    op.drop_column("trips", "center_longitude")
    op.drop_column("trips", "destination_citycode")
    op.drop_column("trips", "destination_adcode")
