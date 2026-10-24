"""One deterministic projection; no model, identity guesses or business writes."""
from datetime import datetime, timedelta
import math

from app.draft_promotion.preparation import digest
from app.place_content.images import project_images


def clock(value):
    return value.isoformat(timespec="minutes") if value is not None else None


def presentation_digest(value):
    # Status and saved-object navigation are server state, not candidate content.
    return digest({k: v for k, v in value.items() if k not in {
        "presentation_hash", "stage", "trip_id", "operation_id", "media_reuse"}})


def candidate_presentation(plan):
    stops = []
    for item in plan.activities:
        place = project_images(item.place) if item.place else None
        end = item.end_time or (datetime.combine(item.day_date, item.planned_start_time)
            + timedelta(minutes=item.duration_minutes)).time()
        # Unverified model prose is not promoted into a venue fact or promise.
        note = place.experience.summary if place and place.experience else ""
        stops.append({"ref": item.ref, "name": place.name if place else item.name,
            "address": place.address if place else None, "day_date": item.day_date.isoformat(),
            "start_time": clock(item.planned_start_time), "end_time": clock(end),
            "duration_minutes": item.duration_minutes, "note": note,
            "estimated_cost_fen": item.estimated_cost_fen, "cost_nature": item.cost_nature,
            "place_ref": place.ref.model_dump(mode="json") if place else None,
            "images": [image.model_dump(mode="json") for image in place.images] if place else []})
    windows = [{"ref": w.ref, "kind": w.kind, "label": w.label,
        "day_date": w.day_date.isoformat(), "start_time": clock(w.start_time),
        "end_time": clock(w.end_time)} for w in plan.windows]
    routes = [{"from_ref": leg.from_ref, "to_ref": leg.to_ref, "day_date": leg.day_date.isoformat(),
        "mode": leg.route.mode, "distance_meters": leg.route.distance_meters,
        "duration_minutes": math.ceil(leg.route.duration_seconds / 60),
        "provider": leg.route.source.provider} for leg in plan.routes]
    narrative = [(s["day_date"], s["start_time"], f"{s['start_time']}去{s['name']}，留{s['duration_minutes']}分钟") for s in stops]
    narrative += [(w["day_date"], w["start_time"] or "", f"{w['start_time']}—{w['end_time']}留作{w['label']}")
        for w in windows if w["start_time"] and w["end_time"]]
    summary = "我建议" + "；".join(row[2] for row in sorted(narrative)) + "。" if narrative else "这份安排保留了指定的空闲时段。"
    summary += '时间按这次候选分配，' + ('交通采用地图估计' if plan.routes else '尚未获得可用路线') + '；实时营业和现场条件仍需核对。'
    if plan.coverage.blockers:
        summary += '当前候选还不能采用：' + '；'.join(plan.coverage.blockers)
    result = {"protocol_version": 2, "draft_id": str(plan.draft_id), "draft_version": plan.draft_version,
        "prepared_id": str(plan.id), "prepared_hash": plan.prepared_hash,
        "stage": "needs_input" if plan.coverage.blockers else "ready",
        "title": plan.title, "city": plan.city, "start_date": plan.constraints.start_date.isoformat(),
        "constraints": plan.schedule_constraints.model_dump(mode="json") if plan.schedule_constraints else None,
        "constraint_checks": [check.model_dump(mode="json") for check in plan.constraint_checks],
        "end_date": plan.end_date.isoformat(), "summary": summary, "stops": stops, "windows": windows,
        "routes": routes, "warnings": list(plan.coverage.missing), "blockers": list(plan.coverage.blockers),
        "change_summary": list(plan.change_summary), "trip_id": None, "operation_id": None}
    result["presentation_hash"] = presentation_digest(result)
    return result
