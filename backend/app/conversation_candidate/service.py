"""Prepare outside transactions; publish draft and presentation in one CAS."""
import asyncio
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update

from app.database import AssistantSession
from app.drafts.contracts import Draft, DraftCreate
from app.drafts.repository import drafts
from app.draft_promotion.contracts import PreviewRequest, PromotionError, ConfirmRequest
from app.draft_promotion.preparation import prepare, bind_hashes
from app.draft_promotion.repository import prepared_plans
from app.requirements import capture_explicit_requirements
from app.requirements import valid_records
from .commands import validate_command, apply_patches, literal_minutes, explicit_interval, quoted_clocks
from .presentation import candidate_presentation
from .binding import conditions_hash


def candidate_action(action, owner, topic):
    return bool(action and action.get("kind") == "itinerary_candidate_v2"
        and action.get("owner_id") == owner and action.get("topic_id") == topic)


async def current_draft(port, action, topic):
    if not candidate_action(action, getattr(port, "owner", None), topic):
        return None
    return await asyncio.to_thread(port.draft_repository.get, port.owner, UUID(action["presentation"]["draft_id"]))


def proposed_name_matches(name, reference, city, source):
    from types import SimpleNamespace
    from app.assistant_research import requested_place_matches
    base, address = name, None
    decorated = re.fullmatch(r"(.+?)[（(]([^（）()]+)[）)]", name)
    if decorated:
        base, address = decorated.groups()
        if address not in source or address not in (reference.get("address") or ""):
            return False
    return requested_place_matches(SimpleNamespace(name=reference.get("name", ""), aliases=reference.get('aliases', [])), base, city)


async def resolve_plan(plan, city, port, history, message, source_refs=None):
    """Never trust model UUIDs or a category result's ranking as identity."""
    from app.place_content.contracts import SearchQuery
    from app.assistant_research import requested_place_matches
    data = plan.model_dump(mode="json")
    from .sources import source_registry
    spans = source_registry(history, message)
    source_refs = source_refs or {}
    if not set(source_refs) <= {item.item_ref for day in plan.days for item in day.items}:
        raise ValueError('候选来源引用含有未知活动。')
    known = [card["place"] for turn in history for card in turn.get("place_cards", [])]
    source = "\n".join([*(turn.get("user", "") for turn in history), message])
    for day in data["days"]:
        # Repeating the global bounds is semantically identical, not a separate
        # daily override unsupported by the formal preferences owner.
        schedule = data["schedule_constraints"]
        if ((day["start_time"] == schedule["daily_start_time"] and day["end_time"] == schedule["daily_end_time"])
            or not explicit_interval(source, day["start_time"], day["end_time"])):
            day["start_time"] = day["end_time"] = None
        for item in day["items"]:
            # Preserve an explicitly chosen canonical scenic name even if the
            # model abbreviated it. The complete suffix must exist in user text.
            if item['name'] + '景区' in source:
                item['name'] += '景区'
            item.update(place_id=None, provider_place_id=None, identity_status="unknown")
            if item['item_ref'] in source_refs:
                bound = spans.get(source_refs[item['item_ref']])
                if bound is None:
                    raise ValueError('候选来源片段已失效，请重新生成。')
                base = re.split(r'[（(]', item['name'])[0]
                if item['kind'] == 'visit' and base not in bound and base.removesuffix('景区') not in bound:
                    raise ValueError('候选来源片段未包含对应地点。')
                # A referenced span is the one authoritative source; never
                # validate its entity then borrow a quantity from another span.
                item['source_quote'] = bound
            if item["source_quote"] and item["source_quote"] not in source:
                raise ValueError("候选条件无法绑定用户原话，请重新说明该项要求。")
            interval = explicit_interval(item["source_quote"], item["start_time"], item["end_time"])
            kind_terms = {'meal': r'餐|吃饭|用餐', 'rest': r'休息|歇|休憩',
                'free_window': r'自由|留白|空白|不安排|空出', 'blank_day': r'留白|空白|不安排'}
            proposed_capacity = (item['kind'] == 'free_window' and item['duration_source'] == 'planning_allocation'
                and explicit_interval(item['source_quote'], schedule['daily_start_time'], schedule['daily_end_time']))
            if item['kind'] == 'free_window' and re.search(r'餐|吃饭|用餐', item['name']) and item['name'] in item['source_quote']:
                kind_terms = {**kind_terms, 'free_window': r'餐|吃饭|用餐'}
            if item['kind'] in kind_terms and not proposed_capacity and not re.search(kind_terms[item['kind']], item['source_quote']):
                raise ValueError('候选窗口缺少对应类型的用户原话。')
            local = [q for q in re.split(r'[，,。；;!?！？\n]', item['source_quote']) if
                (re.split(r'[（(]', item['name'])[0].removesuffix('景区') in q if item['kind'] == 'visit'
                 else re.search(kind_terms.get(item['kind'], r'.'), q))]
            measured = literal_minutes('，'.join(local))
            if item['duration_source'] == 'user_explicit' and measured != [item['duration_minutes']] and not interval:
                raise ValueError('候选的指定时长无法绑定对应活动原话，尚未应用。')
            if item['kind'] in kind_terms and len(measured) == 1 and item['duration_minutes'] != measured[0]:
                raise ValueError('候选窗口时长与用户要求不一致。')
            if item["kind"] not in {"visit", "optional"}:
                continue
            refs = [p for p in known if p.get("city", "").removesuffix("市") == city.removesuffix("市") and
                proposed_name_matches(item["name"], p, city, source)]
            decorated = re.fullmatch(r"(.+?)[（(]([^（）()]+)[）)]", item["name"])
            query = decorated[1] if decorated else item["name"]
            traceable = query in source and (not decorated or decorated[2] in source)
            from app.assistant_capabilities import _non_authorizing_context
            from app.flexible_creation import declared_place_choice
            mention = query.removesuffix("景区")
            polarity = declared_place_choice(mention, message, item["source_quote"])
            if polarity == "excluded" or polarity == "optional" and item["kind"] == "visit":
                raise ValueError(f"「{query}」本轮被排除或仅作备选，不能从讨论内容提升为已安排活动。")
            if mention in message and _non_authorizing_context(message, mention, start=message.rfind(mention)):
                raise ValueError(f"本轮没有确认安排「{query}」，不会从旧讨论恢复它。请明确本次要去的地点。")
            if not traceable and not refs:
                raise ValueError(f"候选中的「{item['name']}」还没有对应已确认的地点，原安排未变。请先确认这处地点。")
            # Model-allocated visit clocks are not an explicit appointment. Let
            # the existing preparer schedule duration/order with real route time.
            if not interval:
                item["start_time"] = item["end_time"] = None
            candidates = {}
            for ref in refs:
                place = await port.service.get_place(UUID(ref["place_id"]), allow_stale=False)
                if place.city and place.city.removesuffix("市") == city.removesuffix("市") and (place.name == ref["name"]):
                    candidates[place.ref.place_id] = place
            if not candidates:
                found = await port.service.search(SearchQuery(query=query, city=city, page_size=12))
                exact = [p for p in found.items if p.city and p.city.removesuffix("市") == city.removesuffix("市")
                    and proposed_name_matches(item["name"], p.model_dump(mode="json"), city, source)]
                # A literal address supplied by the user can disambiguate equal names.
                addressed = [p for p in exact if p.address and p.address in source]
                for place in addressed or exact:
                    candidates[place.ref.place_id] = place
            if len(candidates) == 1:
                place = next(iter(candidates.values()))
                if place.identity_status == "provider_identity" and place.source.freshness == "fresh" and place.source.expires_at > datetime.now(UTC):
                    item.update(place_id=str(place.ref.place_id), provider_place_id=place.ref.external_ref.provider_place_id,
                        identity_status="provider_confirmed", name=place.name)
    return type(plan).model_validate(data)


async def build_candidate(command, decision, message, history, envelope, port, old, *, today, base_presentation=None):
    validate_command(command, message)
    if command.action == "modify":
        if old is None:
            raise ValueError("当前没有可调整的未保存候选，请先生成一份安排。")
        city = (envelope.conversation_memory.get("slots", {}).get("city") or {}).get("value")
        if city and city.removesuffix("市") != old.city.removesuffix("市"):
            raise ValueError("目的地已经变化，请先为新目的地生成候选，旧地点调整未生效。")
        revised = old.model_copy(deep=True)
        revised.plan = apply_patches(old.plan, command, message)
        # A displayed planning-allocation window may have expanded to consume
        # spare capacity. Preserve its actual interval, not its earlier seed.
        if base_presentation:
            from datetime import time
            windows = {w['ref']: w for w in base_presentation.get('windows', [])}
            for day in revised.plan.days:
                for item in day.items:
                    window = windows.get(item.item_ref)
                    if window and window.get('start_time') and window.get('end_time'):
                        start, end = time.fromisoformat(window['start_time']), time.fromisoformat(window['end_time'])
                        duration = (end.hour-start.hour)*60 + end.minute-start.minute
                        item.start_time, item.end_time = start, end
                        item.duration_minutes = duration
        revised.version += 1
    elif command.action == "generate":
        from app.assistant_operation import approved_tool_decision, CreationProposal
        from datetime import timedelta
        plan = command.plan
        if plan is None or plan.schema_version != 2:
            raise ValueError("尚未生成可核对的完整候选，请重试；没有创建旅行。")
        from app.companion_state import destination_from_text
        city = (decision.city or (decision.creation.destination if decision.creation else '')
            or (envelope.conversation_memory.get("slots", {}).get("city") or {}).get("value", "")
            or envelope.browsing_city or destination_from_text(message, planning_authorized=True) or '')
        # V2 is the one operation. Adapt it to the existing date/budget evidence
        # guard without asking the model to repeat the same creation metadata.
        adapter = decision.model_copy(update={"authorization_quote": command.source_quote,
            "creation": CreationProposal(destination=city, start_date=plan.schedule_constraints.start_date,
                end_date=plan.schedule_constraints.start_date + timedelta(days=len(plan.days)-1),
                total_budget_fen=plan.schedule_constraints.total_budget_fen)})
        tool = approved_tool_decision(adapter, message, envelope, today=today)
        if tool.tool != "create_trip":
            raise ValueError(tool.reply)
        if plan.schedule_constraints.start_date != tool.start_date or len(plan.days) != (tool.end_date-tool.start_date).days + 1:
            raise ValueError("候选日期与已确认条件不一致，尚未应用。")
        source = "\n".join([*(turn.get("user", "") for turn in history), message])
        bounds = plan.schedule_constraints
        for clock in (bounds.daily_start_time, bounds.daily_end_time):
            clock_source = message if quoted_clocks(message) else source
            if (clock.hour, clock.minute) not in quoted_clocks(clock_source):
                raise ValueError("请明确每天可安排的开始和结束时间，避免把猜测的时间当成你的要求。")
        if bounds.max_walking_minutes is not None:
            raise ValueError("步行限制需要保留完整作用范围并核实，请先确认该限制后再准备可采用安排。")
        modes = {"walk": r"步行|走路", "driving": r"自驾|开车|驾车", "transit": r"公交|地铁|公共交通"}
        if bounds.transport_mode not in modes or not re.search(modes[bounds.transport_mode], source):
            raise ValueError("请确认步行、自驾或公共交通；不会默认替你选择交通方式。")
        if (plan.schedule_constraints.total_budget_fen != tool.total_budget_fen
            or plan.schedule_constraints.daily_budget_fen is not None):
            raise ValueError("预算的金额或作用范围尚未核实，尚未应用。")
        revised = Draft(id=uuid4(), **DraftCreate(city=tool.destination, title=f"{tool.destination} · 旅行候选",
            day_count=len(plan.days), requirements=tool.preferences).model_dump(), schema_version=2,
            version=1, status="active", saved=False, plan=None, runs=[], updated_at=datetime.now(UTC))
        revised.plan = await resolve_plan(plan, revised.city, port, history, message, command.source_refs)
        revised.requirement_records = capture_explicit_requirements([], revised.requirements,
            scope={"kind": "draft", "draft_id": str(revised.id), "city": revised.city},
            source_ref=f"draft:{revised.id}:create", force=True)
        # The selector is not required to repeat an earlier hard condition in
        # prose. Carry the server's scoped records with their original source.
        for record in valid_records(envelope.requirement_records):
            if record["scope"].get("city") and record["scope"]["city"].removesuffix("市") != revised.city.removesuffix("市"):
                continue
            if record["scope"]["kind"] == "topic" and record["scope"].get("topic_id") != envelope.topic_id:
                continue
            if record["scope"]["kind"] not in {"topic", "global_preference", "day"}:
                continue
            if record["scope"]["kind"] != "global_preference":
                scope = {"kind": "day" if record["scope"]["kind"] == "day" else "draft",
                    "draft_id": str(revised.id), "city": revised.city}
                for key in ("day_index", "date"):
                    if record["scope"].get(key) is not None:
                        scope[key] = record["scope"][key]
                record = {**record, "scope": scope}
            revised.requirement_records.append(record)
    else:
        raise ValueError("该命令不能生成候选。")
    revised.updated_at = datetime.now(UTC)
    preserved = None
    if command.action == 'modify':
        from datetime import time
        if (not base_presentation or base_presentation.get('draft_id') != str(old.id)
            or base_presentation.get('draft_version') != old.version):
            raise ValueError('候选展示版本已变化，请刷新当前候选再修改。')
        preserved = {item['ref']: time.fromisoformat(item['start_time'])
            for key in ('stops','windows') for item in base_presentation.get(key, []) if item.get('start_time')}
    prepared = await prepare(revised, PreviewRequest(expected_version=revised.version,
        start_date=revised.plan.schedule_constraints.start_date), port.service, preserved_starts=preserved)
    if old is not None and command.action == "modify":
        before = {item.item_ref: item for day in old.plan.days for item in day.items}
        prepared.change_summary = [f"{item.name}：{before[item.item_ref].duration_minutes} → {item.duration_minutes}分钟"
            + ("（本次规划建议，可继续调整）" if item.duration_source == "planning_allocation" else "（按你指定的时长调整）")
            for day in revised.plan.days for item in day.items if item.item_ref in before
            and item.duration_minutes != before[item.item_ref].duration_minutes]
        bind_hashes(prepared)
    if len(prepared.requirements) > 2000:
        prepared.coverage.blockers.append("要求超过正式偏好支持的2000字，请缩短后重新准备。")
        bind_hashes(prepared)
    return revised, prepared


async def publish_candidate(db, *, owner, session_id, signature, topic, message_id, message, envelope, draft, prepared, old=None):
    from app.assistant_research import snapshot_signature
    await db.rollback()
    # Existing draft is locked before the conversation, consistent with Accept.
    if old is not None:
        found = (await db.execute(select(drafts.c.version).where(drafts.c.id == str(old.id),
            drafts.c.owner_id == owner).with_for_update())).scalar_one_or_none()
        if found != old.version:
            raise ValueError("候选已有新版本，刚才的修改未生效。")
    row = await db.scalar(select(AssistantSession).where(AssistantSession.id == session_id)
        .with_for_update().execution_options(populate_existing=True))
    if row is None or snapshot_signature(row) != signature:
        await db.rollback()
        raise ValueError("对话已有新决定，刚才的候选未发布。")
    values = dict(version=draft.version, snapshot=draft.model_dump(mode="json"))
    if old is None:
        await db.execute(drafts.insert().values(id=str(draft.id), owner_id=owner, **values))
    else:
        await db.execute(update(drafts).where(drafts.c.id == str(draft.id), drafts.c.owner_id == owner,
            drafts.c.version == old.version).values(**values))
    await db.execute(prepared_plans.insert().values(id=str(prepared.id), owner_id=owner, snapshot=prepared.model_dump(mode="json")))
    view = candidate_presentation(prepared)
    row.pending_action = {"id": str(uuid4()), "kind": "itinerary_candidate_v2", "owner_id": owner,
        "topic_id": topic, "conditions_hash": conditions_hash(envelope), "presentation": view}
    row.messages = [*row.messages, {"id": str(message_id), "user": message, "assistant": view["summary"],
        "context": envelope.model_dump(mode="json"), "tool": "reply", "run_id": None}]
    await db.commit()
    return row


async def decide_candidate(service, owner, session_id, payload):
    """UI and natural language use this exact same authority and writer."""
    if not payload.accept:
        async with service.sessions() as db, db.begin():
            row = await db.scalar(select(AssistantSession).where(AssistantSession.id == session_id).with_for_update())
            action = row.pending_action if row else None
            view = (action or {}).get("presentation", {})
            if (not action or action.get("owner_id") != owner or action.get("kind") != "itinerary_candidate_v2"
                or any(view.get(key) != str(getattr(payload, key)) for key in ("prepared_id", "prepared_hash", "presentation_hash"))):
                raise PromotionError("candidate_publication_changed", "候选已变化，请刷新后重试。")
            row.pending_action = None
            row.messages = [*row.messages, {"id": str(payload.request_id), "user": "放弃这份候选", "assistant": "已撤回这份候选，尚未创建旅行。"}]
            return row
    operation = await service.confirm_atomic(owner, ConfirmRequest(request_id=payload.request_id,
        prepared_id=payload.prepared_id, prepared_hash=payload.prepared_hash, action="create_and_adopt",
        confirmation="创建并采用当前方案"), session_id=session_id, presentation_hash=payload.presentation_hash)
    result = await service.resume(owner, operation.id)
    if result.status != "applied":
        raise PromotionError("candidate_save_incomplete", result.error or "保存未完成，请重新准备并确认。")
    async with service.sessions() as db:
        return await db.get(AssistantSession, session_id)
