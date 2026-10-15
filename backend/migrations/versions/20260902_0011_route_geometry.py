"""persist route geometry and alternatives

Revision ID: 20260902_0011
Revises: 20260902_0010
"""

from alembic import op
import sqlalchemy as sa


revision = "20260902_0011"
down_revision = "20260902_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("route_legs", "route_cache"):
        op.add_column(
            table,
            sa.Column("path", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )
        op.add_column(
            table,
            sa.Column(
                "alternatives", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
            ),
        )
        op.alter_column(table, "path", server_default=None)
        op.alter_column(table, "alternatives", server_default=None)


def downgrade() -> None:
    for table in ("route_cache", "route_legs"):
        op.drop_column(table, "alternatives")
        op.drop_column(table, "path")
