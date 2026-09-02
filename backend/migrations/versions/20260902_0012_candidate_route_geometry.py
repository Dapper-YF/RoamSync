"""persist candidate route geometry

Revision ID: 20260902_0012
Revises: 20260902_0011
"""

from alembic import op
import sqlalchemy as sa


revision = "20260902_0012"
down_revision = "20260902_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidate_route_legs",
        sa.Column("path", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "candidate_route_legs",
        sa.Column(
            "alternatives", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
    )
    op.alter_column("candidate_route_legs", "path", server_default=None)
    op.alter_column("candidate_route_legs", "alternatives", server_default=None)


def downgrade() -> None:
    op.drop_column("candidate_route_legs", "alternatives")
    op.drop_column("candidate_route_legs", "path")
