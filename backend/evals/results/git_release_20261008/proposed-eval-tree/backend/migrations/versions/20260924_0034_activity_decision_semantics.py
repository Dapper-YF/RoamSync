"""Persist activity decision semantics and their provenance.

Revision ID: 20260924_0034
Revises: 20260924_0033
"""

from alembic import op
import sqlalchemy as sa


revision = "20260924_0034"
down_revision = "20260924_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("can_skip", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("activities", sa.Column("minimum_duration_minutes", sa.Integer(), nullable=True))
    op.add_column("activities", sa.Column("importance_source", sa.String(length=20), nullable=False, server_default="unknown"))
    op.add_column("activities", sa.Column("can_skip_source", sa.String(length=20), nullable=False, server_default="system_default"))
    op.add_column("activities", sa.Column("minimum_duration_source", sa.String(length=20), nullable=False, server_default="unknown"))
    op.execute("UPDATE activities SET can_skip = false WHERE importance = 'must_do'")
    op.create_check_constraint("ck_activities_must_do_not_skippable", "activities", "importance != 'must_do' OR can_skip = false")
    op.create_check_constraint("ck_activities_minimum_duration", "activities", "minimum_duration_minutes IS NULL OR (minimum_duration_minutes > 0 AND minimum_duration_minutes <= duration_minutes)")
    for field in ("importance_source", "can_skip_source", "minimum_duration_source"):
        op.create_check_constraint(f"ck_activities_{field}", "activities", f"{field} IN ('user_explicit', 'user_confirmed', 'system_default', 'unknown')")


def downgrade() -> None:
    for field in ("importance_source", "can_skip_source", "minimum_duration_source"):
        op.drop_constraint(f"ck_activities_{field}", "activities", type_="check")
    op.drop_constraint("ck_activities_minimum_duration", "activities", type_="check")
    op.drop_constraint("ck_activities_must_do_not_skippable", "activities", type_="check")
    for field in ("minimum_duration_source", "can_skip_source", "importance_source", "minimum_duration_minutes", "can_skip"):
        op.drop_column("activities", field)
