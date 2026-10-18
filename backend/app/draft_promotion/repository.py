"""Independent tables, deliberately excluded from formal Base.metadata/migrations."""
from sqlalchemy import Column, Integer, JSON, MetaData, String, Table, UniqueConstraint, select, update

from .contracts import Operation, PreparedPlan, PromotionError

metadata = MetaData()
prepared_plans = Table("v2_draft_prepared_plans", metadata,
    Column("id", String(36), primary_key=True),
    Column("owner_id", String(200), nullable=False, index=True),
    Column("snapshot", JSON, nullable=False))
promotions = Table("v2_draft_promotions", metadata,
    Column("id", String(36), primary_key=True),
    Column("owner_id", String(200), nullable=False, index=True),
    Column("request_id", String(36), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("version", Integer, nullable=False),
    Column("snapshot", JSON, nullable=False),
    Column("confirmation_keys", JSON, nullable=False),
    UniqueConstraint("owner_id", "request_id", name="uq_v2_promotion_owner_key"))


async def get_prepared(session, owner, prepared_id):
    row = (await session.execute(select(prepared_plans.c.snapshot).where(
        prepared_plans.c.id == str(prepared_id), prepared_plans.c.owner_id == owner))).first()
    if row is None:
        raise PromotionError("prepared_not_found", "预备方案不存在，请重新准备。", 404)
    return PreparedPlan.model_validate(row[0])


async def get_operation(session, owner, operation_id, *, lock=False):
    query = select(promotions).where(promotions.c.id == str(operation_id), promotions.c.owner_id == owner)
    row = (await session.execute(query.with_for_update() if lock else query)).mappings().first()
    if row is None:
        raise PromotionError("promotion_not_found", "转换记录不存在。", 404)
    return Operation.model_validate(row["snapshot"]), row


async def save_operation(session, operation, row):
    result = await session.execute(update(promotions).where(promotions.c.id == str(operation.id),
        promotions.c.version == row["version"]).values(version=row["version"] + 1,
        snapshot=operation.model_dump(mode="json")))
    if result.rowcount != 1:
        raise PromotionError("promotion_conflict", "状态已更新，请刷新。")
