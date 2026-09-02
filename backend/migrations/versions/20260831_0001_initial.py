"""Create trips and expenses.

Revision ID: 20260831_0001
Revises:
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trips",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("total_budget_fen", sa.BigInteger(), nullable=False),
        sa.Column("daily_budget_fen", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "daily_budget_fen <= total_budget_fen",
            name="ck_trips_daily_not_above_total",
        ),
        sa.CheckConstraint(
            "daily_budget_fen > 0", name="ck_trips_daily_budget_positive"
        ),
        sa.CheckConstraint("end_date >= start_date", name="ck_trips_dates_ordered"),
        sa.CheckConstraint(
            "total_budget_fen > 0", name="ck_trips_total_budget_positive"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "expenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount_fen", sa.BigInteger(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("spent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount_fen > 0", name="ck_expenses_amount_positive"),
        sa.CheckConstraint(
            "category IN ('food', 'transport', 'ticket', 'lodging', 'shopping', 'other')",
            name="ck_expenses_category_allowed",
        ),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trip_id", "idempotency_key", name="uq_expenses_trip_idempotency"
        ),
    )
    op.create_index(
        "ix_expenses_trip_spent_at",
        "expenses",
        ["trip_id", "spent_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_expenses_trip_spent_at", table_name="expenses")
    op.drop_table("expenses")
    op.drop_table("trips")

