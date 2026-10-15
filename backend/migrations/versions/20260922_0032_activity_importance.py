"""add activity importance decision semantics

Revision ID: 20260922_0032
Revises: 20260921_0031
"""

from alembic import op
import sqlalchemy as sa


revision = "20260922_0032"
down_revision = "20260921_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "activities",
        sa.Column(
            "importance",
            sa.String(length=16),
            nullable=False,
            server_default="normal",
        ),
    )
    op.create_check_constraint(
        "ck_activities_importance_allowed",
        "activities",
        "importance IN ('low', 'normal', 'high', 'must_do')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_activities_importance_allowed",
        "activities",
        type_="check",
    )
    op.drop_column("activities", "importance")
