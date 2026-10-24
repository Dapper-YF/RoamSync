"""Identity-preserving adapter to the existing formal Candidate/Validator/Accept."""
import math
from datetime import time
from uuid import UUID, uuid5

from sqlalchemy import select

from app.database import PlaceCandidate, SourceRecord, Trip, TripPreferences, TripArrangementItem
from app.schemas import CandidateActivity, CandidatePlanSnapshot, CandidateRouteLeg
from .contracts import PromotionError
from .preparation import valid_hashes


def place_key(operation, place_id):
    return uuid5(operation.prepared_id, f"place:{operation.id}:{place_id}")


def source_key(operation, place_id):
    return uuid5(operation.prepared_id, f"source:{operation.id}:{place_id}")


def snapshot_for(plan, operation):
    return CandidatePlanSnapshot(explanation="用户明确确认的旅行草稿，按显示方案确定性转换。",
        activities=[CandidateActivity(candidate_id=a.ref, day_date=a.day_date,
            place_candidate_id=place_key(operation, a.place_id), planned_start_time=a.planned_start_time,
            duration_minutes=a.duration_minutes, estimated_cost_fen=a.estimated_cost_fen,
            transport_mode_to_here=a.transport_mode, reason=a.note,
            source_ids=[source_key(operation, a.place_id)]) for a in plan.activities],
        route_legs=[CandidateRouteLeg(day_date=r.day_date, position=r.position,
            from_activity_ref=r.from_ref, to_activity_ref=r.to_ref, mode=r.route.mode,
            distance_meters=r.route.distance_meters, duration_minutes=math.ceil(r.route.duration_seconds / 60),
            provider=r.route.source.provider, is_estimated=False,
            path=[(p.longitude, p.latitude) for p in r.route.path], calculated_at=r.route.source.fetched_at)
            for r in plan.routes])


async def add_places(session, plan, operation):
    for activity in plan.activities:
        place = activity.place
        session.add(SourceRecord(id=source_key(operation, activity.place_id), trip_id=operation.target_trip_id,
            title=f"{place.name} · 地点身份与参考资料（非预订报价）", url=place.source.source_url,
            provider=place.source.provider, queried_at=place.source.fetched_at, confidence="medium"))
    await session.flush()
    for activity in plan.activities:
        place = activity.place
        session.add(PlaceCandidate(id=place_key(operation, activity.place_id), trip_id=operation.target_trip_id,
            source_record_id=source_key(operation, activity.place_id), slug=f"draft-{place_key(operation, activity.place_id)}",
            name=place.name[:160], category="food" if place.category == "food" else "sight",
            neighborhood=place.district or "", description=f"费用性质：{activity.cost_nature}；非实时可售报价。" + activity.note,
            longitude=place.location.longitude, latitude=place.location.latitude,
            suggested_duration_minutes=activity.duration_minutes, estimated_cost_fen=activity.estimated_cost_fen,
            rating=place.rating or 0, tags=[f"canonical_place:{activity.place_id}",
                f"provider_place:amap:{place.ref.external_ref.provider_place_id}",
                f"place_address:{place.address or ''}", f"cost_nature:{activity.cost_nature}"]))
    await session.flush()


def window_values(plan, operation):
    values = []
    for window in plan.windows:
        if len(window.label) > 160:
            raise PromotionError("window_label_too_long", "休息或留白名称过长，请缩短后重新确认。")
        blank = window.kind == "blank_day"
        optional = window.kind == "optional"
        start = None if optional else time(0) if blank else window.start_time
        end = None if optional else time(23, 59) if blank else window.end_time
        if not optional and (start is None or end is None or start >= end):
            raise PromotionError("window_time_required", "休息或留白缺少明确起止时间，尚未保存。")
        values.append({"id": uuid5(operation.id, f"window:{window.ref}"), "trip_id": operation.target_trip_id,
            "kind": "optional" if optional else "free_window", "label": window.label,
            "identity_key": f"draft-window:{window.ref}", "source_ref": f"draft:{plan.draft_id}:{window.ref}",
            "decision_ref": f"candidate:{plan.id}:{window.kind}:{window.ref}", "place_id": None,
            "day_date": window.day_date, "start_time": start, "end_time": end, "activity_id": None})
    return values


async def add_windows(session, plan, operation):
    for values in window_values(plan, operation):
        session.add(TripArrangementItem(**values))
    await session.flush()


async def verify_formal_binding(session, plan, operation, revision, run, trip):
    from app.requirements import promote_requirements, valid_records
    if not valid_hashes(plan) or (operation.content_hash, operation.evidence_hash, operation.prepared_hash) != (
        plan.content_hash, plan.evidence_hash, plan.prepared_hash):
        raise PromotionError("prepared_hash_mismatch", "方案指纹不一致，请重新准备并确认。")
    if (revision.id != operation.target_revision_id or run.id != operation.target_run_id
        or run.trip_id != operation.target_trip_id or revision.trip_id != trip.id
        or revision.planning_run_id != run.id or run.trigger_type != "draft_promotion"
        or revision.status != "pending" or run.status != "awaiting_confirmation"
        or (run.trigger_snapshot or {}).get("promotion_id") != str(operation.id)):
        raise PromotionError("promotion_binding_changed", "候选来源关联已变化，请重新准备并确认。")
    if snapshot_for(plan, operation).model_dump(mode="json") != revision.proposed_snapshot:
        raise PromotionError("candidate_changed", "正式候选与您看到的方案不一致，请重新准备并确认。")
    for values in window_values(plan, operation):
        item = await session.get(TripArrangementItem, values["id"])
        if item is None or any(getattr(item, key) != value for key, value in values.items()):
            raise PromotionError("candidate_window_changed", "正式留白或备选与您看到的候选不一致，尚未采用。")
    c = plan.constraints
    if (trip.version != run.base_trip_version or trip.version != 1 or trip.archived_at is not None
        or trip.start_date != c.start_date or trip.end_date != plan.end_date or trip.destination != plan.city
        or trip.timezone != "Asia/Shanghai" or trip.currency != "CNY"
        or trip.total_budget_fen != c.total_budget_fen or trip.daily_budget_fen != c.daily_budget_fen):
        raise PromotionError("trip_changed", "旅行日期、预算或版本已变化，请检查旅行并重新确认。")
    preferences = await session.scalar(select(TripPreferences).where(TripPreferences.trip_id == trip.id).with_for_update())
    if (preferences is None or preferences.version != 1 or preferences.daily_start_time != c.daily_start_time
        or preferences.daily_end_time != c.daily_end_time or preferences.transport_modes != [c.transport_mode]
        or preferences.max_walking_minutes != c.max_walking_minutes
        or preferences.free_text_requirements != plan.requirements
        or valid_records(preferences.requirement_records) != promote_requirements(plan.requirement_records,
            draft_id=plan.draft_id, trip_id=trip.id, city=trip.destination, start_date=trip.start_date)):
        raise PromotionError("constraints_changed", "正式偏好约束已变化，请重新准备并确认。")
    for a in plan.activities:
        place = await session.get(PlaceCandidate, place_key(operation, a.place_id))
        source = await session.get(SourceRecord, source_key(operation, a.place_id))
        if (place is None or source is None or place.trip_id != trip.id or source.trip_id != trip.id
            or place.source_record_id != source.id or place.name != a.place.name[:160]
            or abs(float(place.longitude) - a.place.location.longitude) > 0.0000006
            or abs(float(place.latitude) - a.place.location.latitude) > 0.0000006
            or place.estimated_cost_fen != a.estimated_cost_fen or place.suggested_duration_minutes != a.duration_minutes
            or source.provider != a.place.source.provider or source.url != a.place.source.source_url
            or f"provider_place:amap:{a.place.ref.external_ref.provider_place_id}" not in place.tags
            or f"place_address:{a.place.address or ''}" not in place.tags
            or f"canonical_place:{a.place_id}" not in place.tags or f"cost_nature:{a.cost_nature}" not in place.tags):
            raise PromotionError("formal_evidence_changed", "正式地点或费用资料已变化，请重新准备并确认。")
