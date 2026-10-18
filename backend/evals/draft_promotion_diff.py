"""Opt-in read-only provider diagnostic for one explicitly selected promotion.

Run inside the isolated API environment. No Draft/Trip/content-cache writes,
no model invocation, no secret/private prose output. Expired plans are diagnostic
comparisons only and cannot acquire authorization from this script.
"""
import argparse
import asyncio
import json
import math
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text

from app.config import get_settings
from app.database import PlanningRun, session_factory
from app.draft_promotion.contracts import Operation, PreparedPlan
from app.draft_promotion.preparation import digest, evidence_values
from app.draft_promotion.repository import prepared_plans, promotions
from app.place_content.contracts import RouteQuery
from app.place_content.provider import AMapContentProvider


def differences(before, after, path=""):
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(set(before) | set(after)):
            result.extend(differences(before.get(key), after.get(key), f"{path}.{key}"))
        return result
    if isinstance(before, list) and isinstance(after, list) and not path.endswith(".path"):
        if len(before) != len(after):
            return [{"field": path, "before_count": len(before), "after_count": len(after)}]
        return [item for index, pair in enumerate(zip(before, after)) for item in differences(*pair, f"{path}[{index}]")]
    if before == after:
        return []
    result = {"field": path, "before_type": type(before).__name__, "after_type": type(after).__name__}
    if all(isinstance(value, (int, float, bool, type(None))) for value in (before, after)):
        result.update(before=before, after=after)
        if path.endswith(".duration_seconds") and isinstance(before, (int, float)) and isinstance(after, (int, float)):
            result.update(before_display_minutes=math.ceil(before / 60), after_display_minutes=math.ceil(after / 60),
                displayed_minutes_changed=math.ceil(before / 60) != math.ceil(after / 60))
    else:
        # Never print place names, addresses, notes, source URLs or full polylines.
        result.update(before_hash=digest(before), after_hash=digest(after))
        if isinstance(before, list) and isinstance(after, list):
            result.update(before_count=len(before), after_count=len(after))
    return [result]


async def main(operation_id):
    async with session_factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION READ ONLY"))
        row = (await session.execute(select(promotions.c.snapshot).where(promotions.c.id == str(operation_id)))).first()
        if row is None:
            raise SystemExit("selected promotion not found")
        op = Operation.model_validate(row[0])
        runs = (await session.scalars(select(PlanningRun).where(PlanningRun.trip_id == op.target_trip_id,
            PlanningRun.trigger_type == "draft_promotion").order_by(PlanningRun.created_at))).all()
        ids = list(dict.fromkeys([*(r.trigger_snapshot["prepared_id"] for r in runs), str(op.prepared_id)]))
        plans = [PreparedPlan.model_validate((await session.execute(select(prepared_plans.c.snapshot).where(
            prepared_plans.c.id == prepared_id))).scalar_one()) for prepared_id in ids]
    provider = AMapContentProvider(get_settings().amap_rest_key)
    for plan in plans:
        refreshed = plan.model_copy(deep=True)
        failures = []
        for activity in refreshed.activities:
            try:
                current = await provider.detail(activity.place.ref)
                if current is None:
                    raise ValueError("identity_missing")
                activity.place = current
            except Exception as exc:
                failures.append({"ref": activity.ref, "error_type": type(exc).__name__})
        by_ref = {a.ref: a for a in refreshed.activities}
        for route in refreshed.routes:
            try:
                route.route = await provider.route(RouteQuery(origin=by_ref[route.from_ref].place.location,
                    destination=by_ref[route.to_ref].place.location, mode=route.route.mode))
            except Exception as exc:
                failures.append({"ref": f"{route.from_ref}->{route.to_ref}", "error_type": type(exc).__name__})
        before, after = evidence_values(plan), evidence_values(refreshed)
        print(json.dumps({"operation_id": str(operation_id), "operation_status_at_read": op.status,
            "prepared_id": str(plan.id), "diagnostic_only": True, "original_expired": plan.expires_at <= datetime.now(UTC),
            "expected_hash": plan.evidence_hash, "stored_recomputed_hash": digest(before), "refreshed_hash": digest(after),
            "differences": differences(before, after), "failures": failures}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operation_id", type=UUID)
    asyncio.run(main(parser.parse_args().operation_id))
