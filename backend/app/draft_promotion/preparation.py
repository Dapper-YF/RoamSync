"""Bounded deterministic date/schedule adapter; no Planner or model invocation."""
import hashlib
import json
import math
from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

from app.place_content.contracts import RouteQuery
from .contracts import Coverage, PreparedActivity, PreparedPlan, PreparedRoute
from app.drafts.service import draft_records
from app.requirements import project_requirements


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def evidence_values(plan):
    # Retrieval/expiry times are checked separately. New retrieval alone is not new fact evidence.
    return {
        "places": [{"id": str(a.place_id), "ref": a.place.ref.model_dump(mode="json"),
            "name": a.place.name, "city": a.place.city, "category": a.place.category,
            "location": a.place.location.model_dump(mode="json"), "price": a.place.price.model_dump(mode="json") if a.place.price else None,
            "price_status": a.place.price_status, "provider": a.place.source.provider,
            "url": a.place.source.source_url, "provider_updated_at": a.place.source.provider_updated_at.isoformat() if a.place.source.provider_updated_at else None}
            for a in plan.activities if a.place],
        "routes": [{"day": r.day_date.isoformat(), "position": r.position,
            "from": r.from_ref, "to": r.to_ref,
            **r.route.model_dump(mode="json", exclude={"source"}),
            "provider": r.route.source.provider, "url": r.route.source.source_url,
            "provider_updated_at": r.route.source.provider_updated_at.isoformat() if r.route.source.provider_updated_at else None}
            for r in plan.routes],
    }


def semantic_values(plan):
    values = {"draft_id": str(plan.draft_id), "draft_version": plan.draft_version,
        "city": plan.city, "requirements": plan.requirements,
        "constraints": plan.constraints.model_dump(mode="json", exclude={"operation_id"}), "end_date": plan.end_date.isoformat(),
        "activities": [a.model_dump(mode="json", exclude={"place", "name", "note"}) for a in plan.activities],
        "routes": [{"day": r.day_date.isoformat(), "position": r.position, "from": r.from_ref, "to": r.to_ref,
            "mode": r.route.mode, "distance_meters": r.route.distance_meters,
            "duration_seconds": r.route.duration_seconds} for r in plan.routes],
        "coverage": plan.coverage.model_dump(mode="json")}
    if plan.requirement_records:
        values["requirement_records"] = plan.requirement_records
    return values


def bind_hashes(plan):
    plan.content_hash = digest(semantic_values(plan))
    plan.evidence_hash = digest(evidence_values(plan))
    plan.prepared_hash = digest({"id": str(plan.id), "operation_id": str(plan.operation_id),
        "content": plan.content_hash, "evidence": plan.evidence_hash, "expires_at": plan.expires_at.isoformat()})
    return plan


def valid_hashes(plan):
    copy = bind_hashes(plan.model_copy(deep=True))
    return (copy.content_hash, copy.evidence_hash, copy.prepared_hash) == (plan.content_hash, plan.evidence_hash, plan.prepared_hash)


def fresh(place, now):
    return place.identity_status == "provider_identity" and place.source.freshness == "fresh" and place.source.expires_at > now


async def prepare(draft, request, places):
    now = datetime.now(UTC)
    blockers, activities, routes, expiries = [], [], [], [now + timedelta(minutes=15)]
    if not draft.plan:
        blockers.append("草稿还没有方案，请先生成并检查草稿。")
    seen = set()
    for day in draft.plan.days if draft.plan else []:
        day_date = request.start_date + timedelta(days=day.day_index - 1)
        cursor = request.daily_start_time.hour * 60 + request.daily_start_time.minute
        previous = None
        if not day.items:
            blockers.append(f"第{day.day_index}天没有活动，请补全草稿。")
        walking_minutes = 0
        for position, item in enumerate(day.items):
            ref = f"day{day.day_index}:item{position}"
            place = None
            if item.place_id and item.identity_status == "provider_confirmed":
                try:
                    place = await places.get_place(item.place_id, allow_stale=False)
                    if (not fresh(place, datetime.now(UTC)) or place.ref.place_id != item.place_id or place.name != item.name
                        or not place.city or place.city.removesuffix("市") != draft.city.removesuffix("市")):
                        place = None
                except Exception:
                    place = None
            if place is None:
                blockers.append(f"第{day.day_index}天「{item.name}」地点身份不明确或数据过期；请修改草稿为搜索中可确认的真实地点后重新准备。")
            else:
                expiries.append(place.source.expires_at)
                if place.ref.place_id in seen:
                    blockers.append(f"「{item.name}」重复出现；请在草稿中明确处理重复地点。")
                seen.add(place.ref.place_id)
            if previous is not None and previous.place and place:
                try:
                    route = await places.query_route(RouteQuery(origin=previous.place.location,
                        destination=place.location, mode=request.transport_mode))
                    if (route.source.freshness != "fresh" or route.source.expires_at <= datetime.now(UTC)
                        or route.origin != previous.place.location or route.destination != place.location or route.mode != request.transport_mode):
                        raise ValueError("route_not_fresh_or_bound")
                    routes.append(PreparedRoute(day_date=day_date, position=position - 1,
                        from_ref=previous.ref, to_ref=ref, route=route))
                    minutes = math.ceil(route.duration_seconds / 60)
                    cursor += minutes
                    if route.mode == "walk":
                        walking_minutes += minutes
                    expiries.append(route.source.expires_at)
                except Exception:
                    blockers.append(f"第{day.day_index}天「{previous.name}→{item.name}」缺少有效真实路线，请重试准备。")
            cost_nature = "provider_reference" if place and place.price and place.price_status == "provider_reference" else "planning_estimate"
            cost = round(place.price.amount * 100) if cost_nature == "provider_reference" else request.unknown_cost_estimate_fen
            activity = PreparedActivity(ref=ref, day_date=day_date, position=position, name=item.name,
                place_id=item.place_id, place=place, planned_start_time=time(min(cursor, 1439) // 60, min(cursor, 1439) % 60),
                duration_minutes=request.duration_minutes, transport_mode=request.transport_mode,
                estimated_cost_fen=cost, cost_nature=cost_nature, note=item.note)
            activities.append(activity)
            cursor += request.duration_minutes
            previous = activity
        if cursor > request.daily_end_time.hour * 60 + request.daily_end_time.minute:
            blockers.append(f"第{day.day_index}天超出每日可用时间；请减少活动或调整时长后重新准备。")
        if walking_minutes > request.max_walking_minutes:
            blockers.append(f"第{day.day_index}天预计步行{walking_minutes}分钟，超过所选{request.max_walking_minutes}分钟；请调整交通或草稿。")
        day_cost = sum(a.estimated_cost_fen for a in activities if a.day_date == day_date)
        if request.daily_budget_fen is not None and day_cost > request.daily_budget_fen:
            blockers.append(f"第{day.day_index}天规划费用{day_cost / 100:.2f}元超过每日预算，请调整预算或草稿。")
    if request.total_budget_fen is not None and sum(a.estimated_cost_fen for a in activities) > request.total_budget_fen:
        blockers.append("规划费用超过总预算，请调整预算或草稿。")
    # Successful modification requests remain part of the explicitly approved
    # requirements, rather than disappearing behind their generated plan text.
    records = draft_records(draft)
    effective = {r["id"]: r for n in range(1, draft.day_count + 1) for r in project_requirements(
        records, draft_id=str(draft.id), city=draft.city, day_index=n)}
    requirements = list(dict.fromkeys(r["text"] for r in effective.values()))
    plan = PreparedPlan(id=uuid4(), draft_id=draft.id, draft_version=draft.version,
        operation_id=request.operation_id, city=draft.city, title=draft.title[:120], requirements="\n".join(requirements),
        requirement_records=records, constraints=request, end_date=request.start_date + timedelta(days=draft.day_count - 1),
        activities=activities, routes=routes,
        coverage=Coverage(checked=["真实地点身份与来源时效", "真实日期、顺序、时长和每日窗口", "相邻地点真实路线和步行上限", "已显示费用与所选预算"],
            missing=["营业时间与预约要求未核实", "酒店、门票库存及实时可售报价未核实", "交通费、住宿、餐饮等未列出项目不计入费用", "其他自由文本特殊要求仅保留原文，未做语义可行性核验", "正式Validator将在已授权创建Trip后再次校验"], blockers=blockers),
        content_hash="", evidence_hash="", prepared_hash="", created_at=now, expires_at=min(expiries))
    return bind_hashes(plan)


async def refresh_equivalent(plan, places):
    """Network work before T3, preserving every approved schedule/value/identity."""
    refreshed = plan.model_copy(deep=True)
    now = datetime.now(UTC)
    if plan.expires_at <= now:
        return None, "预备方案已过期，请重新准备并确认。"
    try:
        for activity in refreshed.activities:
            place = await places.get_place(activity.place_id, allow_stale=False)
            if not fresh(place, datetime.now(UTC)) or place.ref.place_id != activity.place_id:
                raise ValueError("place_expired")
            activity.place = place
        by_ref = {a.ref: a for a in refreshed.activities}
        for leg in refreshed.routes:
            leg.route = await places.query_route(RouteQuery(origin=by_ref[leg.from_ref].place.location,
                destination=by_ref[leg.to_ref].place.location, mode=leg.route.mode))
            if leg.route.source.freshness != "fresh" or leg.route.source.expires_at <= datetime.now(UTC):
                raise ValueError("route_expired")
    except Exception:
        return None, "地点或路线当前无法核实；旅行若已创建将保留，请重新准备并确认。"
    if digest(evidence_values(refreshed)) != plan.evidence_hash:
        return None, "地点、费用参考或路线信息已变化；请查看更新后的完整方案并重新确认。"
    expiry = min([plan.expires_at] + [a.place.source.expires_at for a in refreshed.activities]
        + [r.route.source.expires_at for r in refreshed.routes])
    return {"equivalent": True, "checked_at": datetime.now(UTC).isoformat(),
        "expires_at": expiry.isoformat(), "evidence_hash": plan.evidence_hash,
        "rule": "exact_identity_scope_and_key_values_v1; retrieval_time_ignored"}, None
