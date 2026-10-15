"""Make trip budget limits optional.

Revision ID: 20260914_0021
Revises: 20260910_0020
"""

from alembic import op
import sqlalchemy as sa


revision = "20260914_0021"
down_revision = "20260910_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("trips", "total_budget_fen", existing_type=sa.BigInteger(), nullable=True)
    op.alter_column("trips", "daily_budget_fen", existing_type=sa.BigInteger(), nullable=True)
    op.drop_constraint("ck_trips_total_budget_positive", "trips", type_="check")
    op.drop_constraint("ck_trips_daily_budget_positive", "trips", type_="check")
    op.drop_constraint("ck_trips_daily_not_above_total", "trips", type_="check")
    op.create_check_constraint(
        "ck_trips_budget_limits_consistent",
        "trips",
        "(total_budget_fen IS NULL AND daily_budget_fen IS NULL) OR "
        "(total_budget_fen > 0 AND daily_budget_fen > 0 AND daily_budget_fen <= total_budget_fen)",
    )


def downgrade() -> None:
    raise RuntimeError("cannot downgrade while trips without budget limits exist")
