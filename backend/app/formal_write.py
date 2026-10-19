"""Transaction-local protection for existing formal itinerary commands.

No persisted workflow, candidate or alternate source of truth. Trip is locked
before Day/Activity writes; existing Activity/Requirement versions remain local.
"""
from functools import wraps
import inspect
import json

from sqlalchemy import select

from app.database import Activity, DayPlan, RouteLeg, Trip


class FormalWriteConflictError(Exception):
    pass


async def lock_trip(session, trip_id, *, expected_version=None, detect_concurrent=False):
    if expected_version is None and detect_concurrent:
        expected_version = await session.scalar(select(Trip.version).where(Trip.id == trip_id))
    trip = await session.scalar(select(Trip).where(Trip.id == trip_id).with_for_update().execution_options(populate_existing=True))
    if trip is None or expected_version is not None and trip.version != expected_version:
        raise FormalWriteConflictError("旅行安排已变化，请刷新后重试")
    return trip


async def _state(session, trip_id):
    """Semantic fingerprint only; no timestamps, route row IDs or persisted copy."""
    fields = [c for c in Activity.__table__.columns if c.name not in {"version", "created_at", "updated_at"}]
    rows = (await session.execute(select(*fields, Activity.version).join(DayPlan, Activity.day_plan_id == DayPlan.id).where(DayPlan.trip_id == trip_id))).all()
    activities = {r.id: (tuple(r[:-1]), r.version) for r in rows}
    day_fields = [c for c in DayPlan.__table__.columns if c.name not in {"created_at", "updated_at"}]
    days = (await session.execute(select(*day_fields).where(DayPlan.trip_id == trip_id).order_by(DayPlan.id))).all()
    route_fields = [c for c in RouteLeg.__table__.columns if c.name not in {"id", "calculated_at"}]
    routes = (await session.execute(select(*route_fields).join(DayPlan, RouteLeg.day_plan_id == DayPlan.id).where(DayPlan.trip_id == trip_id).order_by(RouteLeg.day_plan_id, RouteLeg.position))).all()
    encoded = json.dumps({"days": [tuple(d) for d in days], "routes": [tuple(r) for r in routes]}, default=str, sort_keys=True)
    return activities, encoded


async def finish_formal_write(session):
    trip, before, before_other = session.info["formal_write"]
    await session.flush()
    from app.arrangement_service import validate_current_arrangement
    await validate_current_arrangement(session, trip.id)
    after, after_other = await _state(session, trip.id)
    changed_ids = {key for key in before.keys() & after.keys() if before[key][0] != after[key][0]}
    changed = before.keys() != after.keys() or bool(changed_ids) or before_other != after_other
    # Route/schedule recalculation also changes *other* Activity rows. Fence
    # clients editing those rows, not only the originally selected Activity.
    for key in changed_ids:
        if after[key][1] == before[key][1]:
            activity = await session.get(Activity, key)
            activity.version += 1
    if changed:
        trip.version += 1
    await session.commit()


def protect_formal_write(scope, identity_arg):
    """Wrap existing committing commands; preserve arguments and return types."""
    def decorate(fn):
        signature = inspect.signature(fn)
        @wraps(fn)
        async def guarded(*args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            session = bound.arguments["session"]
            identity = bound.arguments[identity_arg]
            if scope == "day":
                trip_id = await session.scalar(select(DayPlan.trip_id).where(DayPlan.id == identity))
            else:
                trip_id = await session.scalar(select(DayPlan.trip_id).join(Activity, Activity.day_plan_id == DayPlan.id).where(Activity.id == identity))
            if trip_id is None:
                return await fn(*args, **kwargs)  # Existing 404 semantics.
            try:
                trip = await lock_trip(session, trip_id, expected_version=bound.arguments.get("expected_trip_version"), detect_concurrent=True)
                before, other = await _state(session, trip.id)
                session.info["formal_write"] = (trip, before, other)
                return await fn(*args, **kwargs)
            except BaseException:
                await session.rollback()
                raise
            finally:
                session.info.pop("formal_write", None)
        return guarded
    return decorate
