"""Bounded deterministic date/schedule adapter; no Planner or model invocation."""
import hashlib
import json
import math
from datetime import UTC, datetime, time, timedelta
from uuid import uuid4

from app.place_content.contracts import RouteQuery
from .contracts import Coverage, PreviewRequest, PreparedActivity, PreparedPlan, PreparedRoute, PreparedWindow, PreparedConstraintCheck, PreparedDayConstraints
from app.drafts.service import draft_records
from app.requirements import project_requirements
from app.drafts.timing import quoted_clocks


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def evidence_values(plan):
    # Retrieval/expiry times are checked separately. New retrieval alone is not new fact evidence.
    values = {
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
    if plan.schema_version == 2:
        values["schema_version"] = 2
        values["media"] = [{"ref": a.ref, "place_id": str(a.place_id),
            "image_status": a.place.image_status,
            "images": [image.model_dump(mode="json") for image in a.place.images]} for a in plan.activities if a.place]
        values["display_places"] = [{"ref": a.ref, "place": a.place.model_dump(mode="json", exclude={"source"})}
            for a in plan.activities if a.place]
    return values


def semantic_values(plan):
    if plan.schema_version == 2:
        values = plan.model_dump(mode="json", exclude={"id", "operation_id", "created_at", "expires_at",
            "content_hash", "evidence_hash", "prepared_hash"})
        values["constraints"].pop("operation_id", None)
        # Provider retrieval timestamps are evidence freshness, not schedule changes.
        values["activities"] = [a.model_dump(mode="json", exclude={"place"}) for a in plan.activities]
        values["routes"] = [{"day": r.day_date.isoformat(), "position": r.position,
            "from": r.from_ref, "to": r.to_ref, "mode": r.route.mode,
            "distance_meters": r.route.distance_meters, "duration_seconds": r.route.duration_seconds} for r in plan.routes]
        return values
    values = {"draft_id": str(plan.draft_id), "draft_version": plan.draft_version,
        "city": plan.city, "requirements": plan.requirements,
        "constraints": plan.constraints.model_dump(mode="json", exclude={"operation_id"}), "end_date": plan.end_date.isoformat(),
        "activities": [a.model_dump(mode="json", exclude={"place", "name", "note", "end_time", "duration_source", "source_quote"}) for a in plan.activities],
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


async def prepare(draft, request, places, *, preserved_starts=None):
    if draft.schema_version == 2:
        return await _prepare_v2(draft, request, places, preserved_starts=preserved_starts)
    if draft.plan is not None and draft.plan.schema_version != 1:
        raise ValueError("draft and plan schema_version must agree")
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


def _minute(value):
    return value.hour * 60 + value.minute


def _time(value):
    # Out-of-bounds schedules remain blocked; never wrap into a different day.
    return time(max(0, min(value, 1439)) // 60, max(0, min(value, 1439)) % 60)


async def _prepare_v2(draft, request, places, *, preserved_starts=None):
    """Prepare only explicit structured schedule; never invent non-place activities."""
    if draft.plan is None or draft.plan.schema_version != 2:
        raise ValueError("v2 preparation requires a v2 draft plan")
    schedule = draft.plan.schedule_constraints
    now = datetime.now(UTC)
    blockers, activities, routes, windows, day_constraints = [], [], [], [], []
    expiries, seen, seen_provider = [now + timedelta(minutes=15)], set(), set()
    supported_transport = schedule.transport_mode in {"walk", "driving"}
    if not supported_transport:
        blockers.append(f"交通方式「{schedule.transport_mode}」暂不支持真实路线核验；当前仅支持步行或驾车，请明确调整。")
    if schedule.max_walking_minutes is not None and schedule.walking_scope != "inter_activity":
        blockers.append("当前只能核验景点间路段步行，不能核验全天、景点内部或连续步行硬条件；请明确调整作用域。")
    if len(draft.plan.days) != draft.day_count:
        blockers.append("草稿天数与结构化日期范围不一致，请重新准备。")
    if len(draft.title) > 120:
        blockers.append("旅行标题超过正式行程支持的120字，请缩短标题后再保存。")
    supported_budget = (schedule.total_budget_fen is None) == (schedule.daily_budget_fen is None)
    if not supported_budget:
        blockers.append("当前正式预算契约要求总预算和每日预算同时提供；原始预算已保留，请补全口径后再保存。")
    if schedule.max_walking_minutes is not None and schedule.max_walking_minutes > 480:
        blockers.append("当前正式步行上限契约最多支持480分钟；原始上限已保留，请调整后再保存。")
    # Preview's historical defaults are not planning authority for v2.
    effective = PreviewRequest.model_validate({**request.model_dump(mode="json"), "start_date": schedule.start_date,
        "daily_start_time": schedule.daily_start_time, "daily_end_time": schedule.daily_end_time,
        "transport_mode": schedule.transport_mode if supported_transport else request.transport_mode,
        "total_budget_fen": schedule.total_budget_fen if supported_budget else None,
        "daily_budget_fen": schedule.daily_budget_fen if supported_budget else None,
        "max_walking_minutes": min(schedule.max_walking_minutes or 480, 480)})
    if request.start_date != schedule.start_date:
        blockers.append("准备请求的开始日期与草稿已确认日期不一致，请刷新候选。")
    for day in draft.plan.days:
        day_date = schedule.start_date + timedelta(days=day.day_index - 1)
        begin = day.start_time or schedule.daily_start_time
        end = day.end_time or schedule.daily_end_time
        day_constraints.append(PreparedDayConstraints(day_index=day.day_index, day_date=day_date,
            title=day.title, start_time=begin, end_time=end))
        if day.start_time is not None or day.end_time is not None:
            blockers.append(f"第{day.day_index}天单独的可用时间覆盖尚未支持正式保存；原始每日边界已保留，请明确调整。")
        cursor, day_end, walking_minutes, previous = _minute(begin), _minute(end), 0, None
        if not day.items:
            blockers.append(f"第{day.day_index}天缺少事项；整天留白请明确使用blank_day。")
        for item in day.items:
            if len(item.name) > 160:
                blockers.append(f"第{day.day_index}天事项名称超过正式行程支持的160字；请缩短名称后再保存，不会截断采用。")
            if item.kind == "blank_day":
                windows.append(PreparedWindow(ref=item.item_ref, kind=item.kind, label=item.name,
                    day_date=day_date, start_time=begin, end_time=end, source_quote=item.source_quote, note=item.note,
                    duration_minutes=day_end - _minute(begin), duration_source=item.duration_source))
                continue
            if item.kind == "optional":
                if item.place_id is not None or item.provider_place_id is not None:
                    blockers.append(f"第{day.day_index}天备选「{item.name}」的正式映射尚不能保留地点身份；请先作为未排程候选讨论，或明确转为活动后重试。")
                if item.start_time is not None or item.end_time is not None or item.duration_minutes is not None:
                    blockers.append(f"第{day.day_index}天备选「{item.name}」的正式映射尚不能保留时间或时长；请保留为无时间的备选，或明确转为活动后重试。")
                if item.start_time is not None:
                    optional_end = _minute(item.end_time) if item.end_time is not None else _minute(item.start_time) + (item.duration_minutes or 0)
                    if _minute(item.start_time) < _minute(begin) or optional_end > day_end:
                        blockers.append(f"第{day.day_index}天可选事项「{item.name}」超出每日可用时间。")
                windows.append(PreparedWindow(ref=item.item_ref, kind=item.kind, label=item.name,
                    day_date=day_date, start_time=item.start_time, end_time=item.end_time,
                    source_quote=item.source_quote, note=item.note, place_id=item.place_id,
                    provider_place_id=item.provider_place_id, duration_minutes=item.duration_minutes,
                    duration_source=item.duration_source))
                continue
            duration = item.duration_minutes
            if duration is None:
                duration = _minute(item.end_time) - _minute(item.start_time)
            start = _minute(item.start_time) if item.start_time is not None else cursor
            anchor = (preserved_starts or {}).get(item.item_ref)
            if anchor is not None:
                start = _minute(anchor)
            if item.kind != "visit":
                clocks = quoted_clocks(item.source_quote)
                fixed = anchor is not None or item.start_time is not None and (item.start_time.hour, item.start_time.minute) in clocks
                if not fixed:
                    start = max(start, cursor)
                if start < cursor:
                    blockers.append(f"第{day.day_index}天「{item.name}」与前一事项重叠。")
                finish = start + duration
                if (item.kind == 'free_window' and item.duration_source == 'planning_allocation'
                    and not fixed and item.end_time == end and start < day_end):
                    finish = day_end
                    duration = finish - start
                elif item.end_time is not None and (item.end_time.hour, item.end_time.minute) in clocks and finish > _minute(item.end_time):
                    blockers.append(f'第{day.day_index}天「{item.name}」超出用户指定的结束时间。')
                windows.append(PreparedWindow(ref=item.item_ref, kind=item.kind, label=item.name, day_date=day_date,
                    start_time=_time(start), end_time=_time(finish), source_quote=item.source_quote, note=item.note,
                    duration_minutes=duration, duration_source=item.duration_source))
                if start < _minute(begin) or finish > day_end:
                    blockers.append(f"第{day.day_index}天「{item.name}」超出每日可用时间。")
                cursor = max(cursor, finish)
                continue
            place = None
            if item.place_id is not None and item.identity_status == "provider_confirmed":
                try:
                    place = await places.get_place(item.place_id, allow_stale=False)
                    if (not fresh(place, datetime.now(UTC)) or place.ref.place_id != item.place_id
                        or not place.ref.external_ref.provider_place_id
                        or (item.provider_place_id and place.ref.external_ref.provider_place_id != item.provider_place_id)
                        or item.name not in {place.name, *place.aliases}
                        or not place.city or place.city.removesuffix("市") != draft.city.removesuffix("市")):
                        place = None
                except Exception:
                    place = None
            if place is None:
                blockers.append(f"第{day.day_index}天「{item.name}」地点身份不明确或数据过期；请使用已核实的真实地点。")
            else:
                expiries.append(place.source.expires_at)
                if len(place.name) > 160:
                    blockers.append(f"第{day.day_index}天真实地点名称超过正式行程支持的160字；请明确调整，不会截断采用。")
                if place.ref.place_id in seen:
                    blockers.append(f"「{item.name}」重复出现；请明确处理重复地点。")
                seen.add(place.ref.place_id)
                provider_identity = (place.ref.external_ref.provider, place.ref.external_ref.namespace,
                    place.ref.external_ref.provider_place_id)
                if provider_identity in seen_provider:
                    blockers.append(f"「{item.name}」的provider地点身份重复出现；请明确处理重复地点。")
                seen_provider.add(provider_identity)
            if previous is not None and previous.place and place and supported_transport:
                try:
                    route = await places.query_route(RouteQuery(origin=previous.place.location,
                        destination=place.location, mode=schedule.transport_mode))
                    if (route.source.freshness != "fresh" or route.source.expires_at <= datetime.now(UTC)
                        or route.origin != previous.place.location or route.destination != place.location
                        or route.mode != schedule.transport_mode):
                        raise ValueError("route_not_fresh_or_bound")
                    routes.append(PreparedRoute(day_date=day_date, position=previous.position,
                        from_ref=previous.ref, to_ref=item.item_ref, route=route))
                    travel = math.ceil(route.duration_seconds / 60)
                    cursor += travel
                    if route.mode == "walk":
                        walking_minutes += travel
                    expiries.append(route.source.expires_at)
                except Exception:
                    blockers.append(f"第{day.day_index}天「{previous.name}→{item.name}」缺少有效真实路线，请重试准备。")
            if item.start_time is None and anchor is None:
                start = cursor
            if start < cursor:
                blockers.append(f"第{day.day_index}天「{item.name}」与前一事项或真实路线重叠。")
            finish = start + duration
            if start < _minute(begin) or finish > day_end:
                blockers.append(f"第{day.day_index}天「{item.name}」超出每日可用时间。")
            nature = "provider_reference" if place and place.price and place.price_status == "provider_reference" else "planning_estimate"
            cost = round(place.price.amount * 100) if nature == "provider_reference" else request.unknown_cost_estimate_fen
            activity = PreparedActivity(ref=item.item_ref, day_date=day_date,
                position=sum(a.day_date == day_date for a in activities), name=item.name,
                place_id=item.place_id, place=place, planned_start_time=_time(start), end_time=_time(finish),
                duration_minutes=duration, duration_source=item.duration_source, source_quote=item.source_quote,
                transport_mode=effective.transport_mode, estimated_cost_fen=cost, cost_nature=nature, note=item.note)
            activities.append(activity)
            cursor, previous = max(cursor, finish), activity
        if schedule.max_walking_minutes is not None and walking_minutes > schedule.max_walking_minutes:
            blockers.append(f"第{day.day_index}天景点间预计步行{walking_minutes}分钟，超过所选{schedule.max_walking_minutes}分钟。")
        day_cost = sum(a.estimated_cost_fen for a in activities if a.day_date == day_date)
        if schedule.daily_budget_fen is not None and day_cost > schedule.daily_budget_fen:
            blockers.append(f"第{day.day_index}天规划费用超过每日预算，请调整预算或草稿。")
    if schedule.total_budget_fen is not None and sum(a.estimated_cost_fen for a in activities) > schedule.total_budget_fen:
        blockers.append("规划费用超过总预算，请调整预算或草稿。")
    records = draft_records(draft)
    applicable = {r["id"]: r for day in draft.plan.days for r in project_requirements(records,
        draft_id=str(draft.id), city=draft.city, day_index=day.day_index,
        target_date=schedule.start_date + timedelta(days=day.day_index - 1),
        target_activity_ids=[item.item_ref for item in day.items])}
    verified = {"start_date": schedule.start_date.isoformat(), "transport_mode": schedule.transport_mode,
        "budget_fen": schedule.total_budget_fen, "daily_budget_fen": schedule.daily_budget_fen,
        "max_walking_minutes": schedule.max_walking_minutes if schedule.walking_scope == "inter_activity" else None}
    checks = []
    for record in applicable.values():
        supported = record["key"] in verified and verified[record["key"]] is not None
        status = "unverified" if not supported else "satisfied" if record["value"] == verified[record["key"]] else "violated"
        if record["key"] == "transport_mode" and not supported_transport:
            status = "unverified"
        # Matching a configured bound is not evidence that the actual route or cost fits it.
        if status == "satisfied" and record["key"] == "max_walking_minutes":
            if any(sum(math.ceil(r.route.duration_seconds / 60) for r in routes if r.day_date == schedule.start_date + timedelta(days=d.day_index-1)
                and r.route.mode == "walk") > record["value"] for d in draft.plan.days
                if (not record["scope"].get("day_index") or d.day_index == record["scope"]["day_index"])
                and (not record["scope"].get("date") or str(schedule.start_date + timedelta(days=d.day_index-1)) == record["scope"]["date"])):
                status = "violated"
            if any(a.place is None for a in activities) or any("真实路线" in b for b in blockers):
                status = "unverified"
        if status == "satisfied" and record["key"] in {"budget_fen", "daily_budget_fen"}:
            # Reference/estimated activity costs do not establish the user's total travel cost.
            status = "unverified"
        checks.append(PreparedConstraintCheck(requirement_ref=record["id"], status=status,
            source_quote=record["text"], source_ref=record["source"]["ref"]))
        if record["strength"] == "hard" and status != "satisfied":
            blockers.append(f"硬条件「{record['text']}」尚无法由当前真实证据核验；请澄清或调整后再保存。")
    requirement_text = "\n".join(dict.fromkeys(r["text"] for r in applicable.values()))
    if len(requirement_text) > 2000:
        blockers.append("旅行要求超过正式偏好支持的2000字，请缩短要求后重新准备；不会截断采用。")
    plan = PreparedPlan(schema_version=2, id=uuid4(), draft_id=draft.id, draft_version=draft.version,
        operation_id=request.operation_id, city=draft.city, title=draft.title,
        requirements=requirement_text, requirement_records=records,
        constraints=effective, schedule_constraints=schedule.model_copy(deep=True),
        end_date=schedule.start_date + timedelta(days=draft.day_count - 1), activities=activities, routes=routes, windows=windows,
        constraint_checks=checks, day_constraints=day_constraints,
        coverage=Coverage(checked=["逐项时长与来源、日期、固定窗口和真实路段", "真实地点canonical/provider身份", "景点间路段步行与所列项目费用"],
            missing=["营业时间、预约和库存未核实", "费用为所列项目参考或规划估计，不包含未列出项目", "景点内部、连续和全天步行未核实", "保存前会再次核对活动、路线和行程限制"],
            blockers=list(dict.fromkeys(blockers))), content_hash="", evidence_hash="", prepared_hash="", created_at=now, expires_at=min(expiries))
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
        return None, ("地点或路线当前无法核实，请重新准备并确认。" if plan.schema_version == 2
            else "地点或路线当前无法核实；旅行若已创建将保留，请重新准备并确认。")
    if digest(evidence_values(refreshed)) != plan.evidence_hash:
        return None, "地点、费用参考或路线信息已变化；请查看更新后的完整方案并重新确认。"
    expiry = min([plan.expires_at] + [a.place.source.expires_at for a in refreshed.activities]
        + [r.route.source.expires_at for r in refreshed.routes])
    return {"equivalent": True, "checked_at": datetime.now(UTC).isoformat(),
        "expires_at": expiry.isoformat(), "evidence_hash": plan.evidence_hash,
        "rule": "exact_identity_scope_and_key_values_v1; retrieval_time_ignored"}, None
