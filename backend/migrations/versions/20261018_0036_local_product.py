"""Add persisted product tables without importing preview data or touching trips."""
from alembic import op
import sqlalchemy as sa

revision = "20261018_0036"
down_revision = "20261016_0035"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("v2_content_places",
        sa.Column("place_id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("namespace", sa.String(30), nullable=False),
        sa.Column("provider_place_id", sa.String(100), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False))
    op.create_index("uq_v2_content_external_identity", "v2_content_places",
                    ["provider", "namespace", "provider_place_id"], unique=True)
    op.create_table("v2_content_favorites",
        sa.Column("owner_id", sa.String(200), primary_key=True),
        sa.Column("place_id", sa.String(36), sa.ForeignKey("v2_content_places.place_id"), primary_key=True),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_v2_content_favorites_owner_saved", "v2_content_favorites", ["owner_id", "saved_at"])
    op.create_table("v2_travel_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(200), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False))
    op.create_index("ix_v2_travel_drafts_owner_id", "v2_travel_drafts", ["owner_id"])
    op.create_table("v2_travel_preferences",
        sa.Column("owner_id", sa.String(200), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("v2_draft_prepared_plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(200), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False))
    op.create_index("ix_v2_draft_prepared_plans_owner_id", "v2_draft_prepared_plans", ["owner_id"])
    op.create_table("v2_draft_promotions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(200), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("confirmation_keys", sa.JSON(), nullable=False),
        sa.UniqueConstraint("owner_id", "request_id", name="uq_v2_promotion_owner_key"))
    op.create_index("ix_v2_draft_promotions_owner_id", "v2_draft_promotions", ["owner_id"])


def downgrade():
    raise RuntimeError("Product tables may hold user decisions; keep the additive schema when rolling back images")
