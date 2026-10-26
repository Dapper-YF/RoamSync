"""add editable activity metadata

Revision ID: 20260901_0006
Revises: 20260901_0005
"""

from alembic import op
import sqlalchemy as sa

revision = "20260901_0006"
down_revision = "20260901_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("custom_name", sa.String(160), nullable=True))
    op.add_column(
        "activities",
        sa.Column("schedule_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "activities",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint("ck_activities_version_positive", "activities", "version > 0")


def downgrade() -> None:
    op.drop_constraint("ck_activities_version_positive", "activities", type_="check")
    op.drop_column("activities", "version")
    op.drop_column("activities", "schedule_locked")
    op.drop_column("activities", "custom_name")
