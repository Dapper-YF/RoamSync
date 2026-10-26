"""Add worker lease fields to planning runs."""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260907_0016"
down_revision: str | None = "20260903_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("planning_runs", sa.Column("worker_id", sa.String(length=80), nullable=True))
    op.add_column(
        "planning_runs",
        sa.Column("worker_lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_planning_runs_worker_lease",
        "planning_runs",
        ["status", "worker_lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_planning_runs_worker_lease", table_name="planning_runs")
    op.drop_column("planning_runs", "worker_lease_expires_at")
    op.drop_column("planning_runs", "worker_id")
