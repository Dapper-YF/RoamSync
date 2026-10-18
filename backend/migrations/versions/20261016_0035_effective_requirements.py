"""Keep explicit scoped requirements on the existing trip preference owner.

Only an additive column; no historical text or itinerary is rewritten.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261016_0035"
down_revision = "20260924_0034"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("trip_preferences", sa.Column(
        "requirement_records", sa.JSON(), nullable=False, server_default=sa.text("'[]'"),
    ))


def downgrade():
    raise RuntimeError("Requirements contain user decisions; destructive downgrade is not supported")
