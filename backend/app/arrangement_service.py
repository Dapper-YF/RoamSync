"""Finite choices owned by Trip; Activity alone owns precise schedules."""
from datetime import date, time
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict, model_validator
from sqlalchemy import delete, select

from app.database import Activity, DayPlan, PlaceCandidate, RouteLeg, Trip, TripArrangementItem
from app.formal_write import lock_trip
from app.maps_service import validate_day_time_bounds


class ArrangementConstraintError(ValueError):
    pass


class ItemWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    expected_version: int = Field(ge=1)
    kind: Literal["selected", "optional", "free_window", "cancelled"]
    label: str = Field(min_length=1, max_length=160)
    source_ref: str = Field(min_length=1, max_length=200)
    place_id: UUID | None = None
    day_date: date | None = None
    start: time | None = None
    end: time | None = None

    @model_validator(mode="after")
    def precision(self):
        if not self.label.strip() or not self.source_ref.strip():
            raise ValueError("名称和决定来源不能为空")
        if self.kind == "free_window":
            if self.day_date is None or self.start is None or self.end is None or self.start >= self.end or self.place_id:
                raise ValueError("留白需要明确日期及起止时间，不能是地点")
        elif self.start is not None or self.end is not None:
            raise ValueError("未排程事项不能附带虚构时间")
        return self


class ItemSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    day_plan_id: UUID
    scheduled_time: time
    duration_minutes: int = Field(ge=5, le=1440)
    schedule_locked: bool = False
    place_id: UUID | None = None


def item_dict(row):
    return {"id": row.id, "trip_id": row.trip_id, "kind": row.kind, "label": row.label,
            "source_ref": row.source_ref, "decision_ref": row.decision_ref, "place_id": row.place_id,
            "day_date": row.day_date, "start": row.start_time, "end": row.end_time, "activity_id": row.activity_id}


async def read_items(session, trip_id):
    return list((await session.scalars(select(TripArrangementItem).where(TripArrangementItem.trip_id == trip_id).order_by(TripArrangementItem.id))).all())


def identity(data):
    if data.kind == "free_window":
        return f"window:{data.day_date}:{data.start}:{data.end}"
    return f"place:{data.place_id}" if data.place_id else "name:" + "".join(data.label.split()).casefold()


async def check_item(session, trip, data):
    if data.day_date and not trip.start_date <= data.day_date <= trip.end_date:
        raise ValueError("日期不在这次旅行范围内")
    if data.place_id:
        place = await session.get(PlaceCandidate, data.place_id)
        if place is None or place.trip_id != trip.id:
            raise ValueError("地点不属于这次旅行")


async def write_item(session, trip_id, data: ItemWrite, *, item_id=None, commit=True):
    trip = await lock_trip(session, trip_id, expected_version=data.expected_version)
    await check_item(session, trip, data)
    row = await session.get(TripArrangementItem, item_id or data.id)
    if row and row.trip_id != trip_id:
        raise ValueError("事项不属于这次旅行")
    if item_id and row is None:
        raise LookupError("事项不存在")
    if row and item_id is None:
        raise ValueError("事项编号已存在，请修改原事项")
    if row and row.activity_id and data.kind != "selected":
        from app.database import ActivityExecution
        activity = await session.get(Activity, row.activity_id)
        lived = await session.scalar(select(ActivityExecution.id).where(ActivityExecution.activity_id == row.activity_id, ActivityExecution.status.in_(["arrived", "in_progress", "completed", "skipped"])))
        if activity is None or activity.schedule_locked or activity.status != "planned" or lived:
            raise ValueError("固定活动或已经发生的活动需先核对影响，不能直接改为备选")
        row.activity_id = None
        await session.flush()
        await session.execute(delete(RouteLeg).where(RouteLeg.day_plan_id == activity.day_plan_id))
        day_id = activity.day_plan_id
        await session.delete(activity)
        await session.flush()
        remaining = list((await session.scalars(select(Activity).where(Activity.day_plan_id == day_id).order_by(Activity.position))).all())
        old_positions = {a.id: a.position for a in remaining}
        for a in remaining:
            a.position += 10000
        await session.flush()
        for position, a in enumerate(remaining):
            a.position = position
            if old_positions[a.id] != position:
                a.version += 1
    if row and row.activity_id and (data.place_id != row.place_id or data.day_date is not None or data.label.strip() != row.label):
        raise ValueError("具体活动的地点、日期或名称请使用活动编辑，不能维护两份结果")
    duplicate = await session.scalar(select(TripArrangementItem.id).where(
        TripArrangementItem.trip_id == trip_id, TripArrangementItem.identity_key == identity(data), TripArrangementItem.id != (row.id if row else data.id)))
    if duplicate:
        raise ValueError("同一事项已存在，请修改原事项")
    if data.place_id and not (row and row.activity_id):
        planned = await session.scalar(select(Activity.id).join(DayPlan).where(DayPlan.trip_id == trip_id, Activity.place_candidate_id == data.place_id))
        if planned:
            raise ValueError("该地点已在具体安排中，不能重复添加")
    if row is None:
        row = TripArrangementItem(id=data.id, trip_id=trip_id, source_ref=data.source_ref, activity_id=None)
        session.add(row)
    before = item_dict(row)
    row.kind, row.label, row.identity_key = data.kind, data.label.strip(), identity(data)
    row.decision_ref, row.place_id, row.day_date = data.source_ref, data.place_id, data.day_date
    row.start_time, row.end_time = data.start, data.end
    await session.flush()
    await validate_current_arrangement(session, trip_id)
    if before != item_dict(row):
        trip.version += 1
    if commit:
        await session.commit()
    return row


async def schedule_item(session, trip_id, item_id, data: ItemSchedule, *, commit=True):
    trip = await lock_trip(session, trip_id, expected_version=data.expected_version)
    from app.database import TripExecution
    if await session.scalar(select(TripExecution.id).where(TripExecution.trip_id == trip_id, TripExecution.status.in_(["in_progress", "paused"]))):
        raise ValueError("旅行进行中，具体时间需通过调整建议协调；未排程选择仍可直接修改")
    item = await session.get(TripArrangementItem, item_id)
    day = await session.get(DayPlan, data.day_plan_id)
    if item is None or item.trip_id != trip_id:
        raise LookupError("事项不存在")
    if item.kind not in {"selected", "optional"} or item.activity_id:
        raise ValueError("该事项不能重复排程")
    if day is None or day.trip_id != trip_id:
        raise ValueError("日期不属于这次旅行")
    place = await session.get(PlaceCandidate, data.place_id or item.place_id) if (data.place_id or item.place_id) else None
    if place is None or place.trip_id != trip_id:
        raise ValueError("需先核实并选择这次旅行中的地点身份")
    if item.place_id and item.place_id != place.id:
        raise ValueError("不能用排程操作偷偷替换地点")
    duplicate = await session.scalar(select(Activity.id).join(DayPlan).where(DayPlan.trip_id == trip_id, Activity.place_candidate_id == place.id))
    if duplicate:
        raise ValueError("该地点已经排程")
    other = await session.scalar(select(TripArrangementItem.id).where(TripArrangementItem.trip_id == trip_id, TripArrangementItem.place_id == place.id, TripArrangementItem.id != item.id))
    if other:
        raise ValueError("地点属于另一事项，请先核对重复选择")
    count = len(list((await session.scalars(select(Activity.id).where(Activity.day_plan_id == day.id))).all()))
    activity = Activity(day_plan_id=day.id, place_candidate_id=place.id, scheduled_time=data.scheduled_time,
        duration_minutes=data.duration_minutes, estimated_cost_fen=place.estimated_cost_fen,
        position=count, status="planned", schedule_locked=data.schedule_locked)
    session.add(activity)
    await session.flush()
    ordered = list((await session.scalars(select(Activity).where(Activity.day_plan_id == day.id).order_by(Activity.scheduled_time, Activity.id))).all())
    old_positions = {a.id: a.position for a in ordered}
    for a in ordered:
        a.position += 10000
    await session.flush()
    for position, a in enumerate(ordered):
        a.position = position
        if a.id != activity.id and old_positions[a.id] != position:
            a.version += 1
    item.activity_id, item.place_id, item.kind = activity.id, place.id, "selected"
    item.identity_key, item.day_date = f"place:{place.id}", None
    # Inserting a stop invalidates old adjacency facts, not the user's times.
    await session.execute(delete(RouteLeg).where(RouteLeg.day_plan_id == day.id))
    await session.flush()
    await validate_current_arrangement(session, trip_id)
    await validate_day_time_bounds(session, day.id)
    trip.version += 1
    if commit:
        await session.commit()
    return item


async def cancel_activity_choices(session, activity_ids):
    rows = (await session.scalars(select(TripArrangementItem).where(TripArrangementItem.activity_id.in_(activity_ids)))).all()
    for item in rows:
        item.decision_ref = f"activity-delete:{item.activity_id}"
        item.activity_id, item.kind = None, "cancelled"


async def validate_current_arrangement(session, trip_id):
    """No inferred times; protect explicit windows and prevent double counting."""
    rows = await read_items(session, trip_id)
    if not rows:
        return
    trip = await session.get(Trip, trip_id)
    activities = (await session.execute(select(Activity, DayPlan.date).join(DayPlan).where(DayPlan.trip_id == trip_id))).all()
    by_id = {a.id: a for a, _ in activities}
    minute = lambda t: t.hour * 60 + t.minute
    for item in rows:
        if item.activity_id and (item.activity_id not in by_id or by_id[item.activity_id].place_candidate_id != item.place_id):
            raise ArrangementConstraintError("事项与具体活动的身份或地点不一致")
        if item.kind != "cancelled" and item.day_date and not trip.start_date <= item.day_date <= trip.end_date:
            raise ArrangementConstraintError("已有留白或日期提示超出新日期，请先核对这些事项")
        if item.kind == "free_window":
            for activity, day in activities:
                start = minute(activity.scheduled_time)
                if day == item.day_date and start < minute(item.end_time) and start + activity.duration_minutes > minute(item.start_time):
                    raise ArrangementConstraintError("安排侵入了用户明确保留的空闲时间")
        elif item.kind != "cancelled" and item.place_id:
            if any(a.place_candidate_id == item.place_id and a.id != item.activity_id for a, _ in activities):
                raise ArrangementConstraintError("未排程事项与具体活动重复，需要受控关联")
    ordered = sorted(activities, key=lambda pair: (pair[1], pair[0].scheduled_time))
    for (a, da), (b, db) in zip(ordered, ordered[1:]):
        if da == db and minute(a.scheduled_time) + a.duration_minutes > minute(b.scheduled_time):
            raise ArrangementConstraintError("具体活动时间重叠，需要先处理冲突")
    for leg in (await session.scalars(select(RouteLeg).join(DayPlan).where(DayPlan.trip_id == trip_id))).all():
        a, b = by_id.get(leg.from_activity_id), by_id.get(leg.to_activity_id)
        if a is None or b is None:
            continue
        day = await session.get(DayPlan, a.day_plan_id)
        windows = [i for i in rows if i.kind == "free_window" and i.day_date == day.date]
        if not windows:
            continue
        available = [(minute(a.scheduled_time) + a.duration_minutes, minute(b.scheduled_time))]
        for i in windows:
            left, right = minute(i.start_time), minute(i.end_time)
            available = [(l, r) for x, y in available for l, r in ((x, min(y, left)), (max(x, right), y)) if l < r]
        if max((r-l for l, r in available), default=0) < leg.duration_minutes:
            raise ArrangementConstraintError("已知路线无法在保留空闲之外完成")


async def free_days(session, trip_id):
    return {i.day_date for i in await read_items(session, trip_id)
            if i.kind == "free_window" and i.start_time == time(0) and i.end_time == time(23, 59)}


async def shift_choice_dates(session, trip, start, end):
    from datetime import timedelta
    rows = await read_items(session, trip.id)
    affected = [i for i in rows if i.kind != "cancelled" and i.day_date is not None]
    for i in affected:
        if i.kind == "free_window":
            i.identity_key = f"shift:{i.id}"
    await session.flush()
    for i in affected:
        target = start + timedelta(days=(i.day_date-trip.start_date).days)
        i.decision_ref = f"reschedule:{start}:{end}"
        if target > end:
            i.kind, i.start_time, i.end_time = "cancelled", None, None
            i.identity_key = f"cancelled:{i.id}"
        else:
            i.day_date = target
            if i.kind == "free_window":
                i.identity_key = f"window:{target}:{i.start_time}:{i.end_time}"


async def candidate_item_errors(session, trip_id, snapshot, protected, day_by_id):
    from app.schemas import PlanValidationIssue
    items = await read_items(session, trip_id)
    if not items:
        return []
    errors = []
    def issue(code, message):
        errors.append(PlanValidationIssue(code=code, message=message))
    active = {str(i.id): i for i in items if i.kind != "cancelled"}
    replacements = {a.replaces_activity_id for a in snapshot.activities}
    for item in active.values():
        if item.activity_id:
            kept = item.activity_id in protected and item.activity_id not in replacements
            kept = kept or any(a.replaces_activity_id == item.activity_id and a.place_candidate_id == item.place_id for a in snapshot.activities)
            if not kept:
                issue("arrangement_decision_omitted", "候选遗漏已采用的事项；需要先明确撤销决定")
        elif item.place_id:
            if any(a.place_candidate_id == item.place_id and a.candidate_id != f"arrangement:{item.id}" for a in snapshot.activities):
                issue("arrangement_identity_required", "将未排程事项排程时必须保持其稳定身份")
    for a in snapshot.activities:
        if a.candidate_id.startswith("arrangement:"):
            item = active.get(a.candidate_id.removeprefix("arrangement:"))
            if item is None or item.kind == "free_window" or item.activity_id or item.place_id != a.place_candidate_id:
                issue("arrangement_identity_invalid", "候选事项身份、地点或当前关联已变化")
    minute = lambda t: t.hour * 60 + t.minute
    stops = [(a.day_date, minute(a.planned_start_time), a.duration_minutes) for a in snapshot.activities]
    stops += [(day_by_id[a.day_plan_id].date, minute(a.scheduled_time), a.duration_minutes)
              for a in protected.values() if a.id not in replacements]
    windows = [i for i in items if i.kind == "free_window"]
    for day, start, duration in stops:
        if any(i.day_date == day and start < minute(i.end_time) and start + duration > minute(i.start_time) for i in windows):
            issue("arrangement_free_window_conflict", "候选侵入用户明确保留的空闲时间")
    # Known travel must fit contiguously outside reserved free intervals too.
    by_ref = {a.candidate_id: a for a in snapshot.activities}
    for leg in snapshot.route_legs:
        a, b = by_ref.get(leg.from_activity_ref), by_ref.get(leg.to_activity_ref)
        if a is None or b is None:
            continue  # The existing Validator owns malformed route identities.
        low = minute(a.planned_start_time) + a.duration_minutes
        high = minute(b.planned_start_time)
        available = [(low, high)]
        for i in windows:
            if i.day_date != leg.day_date:
                continue
            left, right = minute(i.start_time), minute(i.end_time)
            available = [(l, r) for x, y in available for l, r in ((x, min(y, left)), (max(x, right), y)) if l < r]
        if windows and max((r-l for l, r in available), default=0) < leg.duration_minutes:
            issue("arrangement_free_window_travel_conflict", "路线耗时无法在保留空闲之外完成")
    return errors


async def bind_accepted_items(session, trip_id, snapshot, activities_by_ref, revision_id):
    rows = {str(i.id): i for i in await read_items(session, trip_id)}
    for candidate in snapshot.activities:
        if candidate.candidate_id.startswith("arrangement:"):
            item = rows[candidate.candidate_id.removeprefix("arrangement:")]
            item.activity_id = activities_by_ref[candidate.candidate_id].id
            item.kind, item.day_date = "selected", None
            item.decision_ref = f"accept:{revision_id}"
