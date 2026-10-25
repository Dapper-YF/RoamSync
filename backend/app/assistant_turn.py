"""Snapshot/read/revalidate/persist boundary for semantic assistant turns."""
import asyncio
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.assistant_capabilities import (CapabilityDecision, answer_with_capabilities,
    decision_goal, failure_bundle, select_capabilities, validate_decision)
from app.assistant_context import ContextEnvelope, restore_context, capture_requirements, capture_effective_requirements
from app.assistant_reliability import TurnDiagnostics, active_turn, bounded_call
from app.assistant_research import snapshot_signature
from app.database import AssistantSession
from app.travel_goal_router import route_travel_goal
from app.draft_promotion.contracts import PromotionError
from app.conversation_candidate.binding import conditions_hash


async def semantic_turn(db, session_id, message, message_id, incoming, port, settings, selector=None, *, city_search=None,
                        selected_day_id=None, selected_activity_id=None):
    from app.assistant_service import AssistantToolError
    captured_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    intentions = []
    focused_name = None
    legacy = incoming is None
    envelope = ContextEnvelope.model_validate(incoming or {"topic_id": "legacy"})
    row = await db.scalar(select(AssistantSession).where(AssistantSession.id == session_id)
        .with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise AssistantToolError("对话不存在，请重新打开助手。")
    if any(m.get("id") == str(message_id) for m in row.messages):
        return row, None, {}
    # Persist receipt time before network work. A failed attempt retried after
    # midnight with the same message ID must not move the user's "tomorrow".
    capture_key = f"message-capture:{message_id}"
    receipt = (row.applied_actions or {}).get(capture_key)
    if isinstance(receipt, str):
        captured_at = datetime.fromisoformat(receipt).astimezone(ZoneInfo("Asia/Shanghai"))
    else:
        row.applied_actions = {**(row.applied_actions or {}), capture_key: captured_at.isoformat()}
    source_messages = [m for m in row.messages if not m.get("context") or m["context"].get("topic_id") == "legacy"] if legacy else list(row.messages)
    envelope, history = restore_context(envelope, source_messages)
    if legacy:
        if not envelope.conversation_memory.get("epoch"):
            history = source_messages
        envelope = envelope.model_copy(update={"read_trip_id": row.trip_id})
    from app.assistant_memory import apply_memory, reset_requested, bootstrap_memory, literal_conditions
    envelope = bootstrap_memory(envelope, history)
    if reset_requested(message):
        envelope, history, _ = apply_memory(envelope, history, message, message_id)
    envelope, history, literal_changed = apply_memory(envelope, history, message, message_id, literal_conditions(message), today=captured_at.date())
    signature = snapshot_signature(row)
    trip_id = envelope.read_trip_id or (None if envelope.conversation_memory.get("detached_trip") else row.trip_id)
    summary = None
    read_snapshot = None
    if trip_id:
        from app.saved_trip_reads import load_saved_trip_read
        try:
            read_snapshot = await load_saved_trip_read(db, trip_id, message,
                selected_day_id=selected_day_id, selected_activity_id=selected_activity_id,
                revision_ref={'id':envelope.action_target.revision_id,'hash':envelope.action_target.revision_hash,
                    'run_id':row.latest_run_id} if envelope.action_target and envelope.action_target.revision_id
                    and envelope.action_target.revision_hash and row.latest_run_id else None)
        except ValueError as exc:
            raise AssistantToolError(str(exc)) from exc
        summary = read_snapshot.selection_summary(message)
    envelope = capture_effective_requirements(capture_requirements(envelope, message), message, message_id=message_id)
    baseline = route_travel_goal(message, history[-12:], pending_action=row.pending_action)
    candidate_snapshot = None if reset_requested(message) else row.pending_action
    await db.commit()
    from app.conversation_candidate.service import current_draft, candidate_action
    candidate = await current_draft(port, candidate_snapshot, envelope.topic_id) if getattr(port, "draft_repository", None) else None
    if candidate:
        summary = {**(summary or {}), "candidate": {"draft_id": str(candidate.id), "version": candidate.version,
            "city": candidate.city, "plan": candidate.plan.model_dump(mode="json")}}
    original_port = port
    class CachedReads:
        def __init__(self):
            self.places = {}
        def __getattr__(self, name):
            return getattr(original_port, name)
        async def get_place(self, place_id):
            key = str(place_id)
            if key not in self.places:
                self.places[key] = await original_port.get_place(place_id)
            return self.places[key]
    port = CachedReads()
    diagnostics = TurnDiagnostics(str(message_id))
    token = active_turn.set(diagnostics)
    independent_read=None
    read_status=None
    try:
        try:
            async with asyncio.timeout(diagnostics.remaining()):
                # A persisted planning clarification may consume a field answer,
                # without minting new mutation authority from a date/budget.
                if ("planning_field_follow_up" in baseline.signals and history
                    and history[-1].get("goal_routing", {}).get("target_runtime") == "planning"):
                    diagnostics.selection = {"intent": "create", "capabilities": [],
                        "reason_code": "planning_field_follow_up", "argument_source": "saved_planning_dialogue"}
                    return None, baseline, {"execution_summary": diagnostics.summary("complete"), "_semantic_context": envelope.model_dump(mode="json"), "_semantic_history_ids": [str(m.get("id")) for m in history]}
                # A focused UI place is provenance too, not permission to mutate.
                if envelope.discussing_place_id:
                    place = await bounded_call(lambda: port.get_place(envelope.discussing_place_id), stage="place_context", limit=8)
                    if place:
                        focused_name = place.name
                        history = [*history, {"user": "", "place_cards": [{"place": place.model_dump(mode="json")}]}]
                changed = list(literal_changed)
                try:
                    if envelope.route_request:
                        decision = CapabilityDecision(intent="route", capabilities=["route"], reason_code="route_requested")
                    else:
                        decision = await (selector or select_capabilities)(settings, message, history, envelope, summary)
                    updates = list(decision.memory_updates)
                    from app.assistant_memory import candidate_scalar_updates
                    updates.extend(candidate_scalar_updates(decision, message, today=captured_at.date()))
                    literal_city = decision.city.removesuffix("市")
                    # A validated, explicitly mentioned conversational city must
                    # not disappear just because the selector omitted its duplicate
                    # memory patch. Comparisons, quoted and hypothetical cities
                    # still pass the same user-evidence guards below.
                    if (literal_city and literal_city in message and not any(u.field == "city" for u in updates)
                        and not ("city" in literal_changed and "city" in envelope.conversation_memory.get("withdrawn", {}))
                        and not re.search(re.escape(literal_city) + r"(?:市)?(?:和|与|还是|或|、)|(?:和|与|还是|或|、)" + re.escape(literal_city), message)):
                        from app.assistant_memory import MemoryUpdate
                        updates.append(MemoryUpdate(field="city", value=literal_city, source_quote=literal_city))
                    envelope, history, selected_changed = apply_memory(envelope, history, message, message_id, updates, today=captured_at.date())
                    changed = list(dict.fromkeys([*changed, *selected_changed]))
                    if changed:
                        diagnostics.record("context", "completed", fields=list(dict.fromkeys(changed)))
                    if envelope.conversation_memory.get("detached_trip") and not envelope.read_trip_id:
                        trip_id, summary, read_snapshot = None, None, None
                    # The corrected conversational city wins over an older UI city.
                    city = (envelope.conversation_memory.get("slots", {}).get("city") or {}).get("value")
                    if city and decision.city and decision.city not in message:
                        decision = decision.model_copy(update={"city": city})
                    decision = validate_decision(decision, message, history, envelope,
                        [*[c["place"] for m in history[-3:] for c in m.get("place_cards", [])],
                         *([{"city": summary["destination"]}] if summary and summary.get("destination") else [])])
                except Exception as exc:
                    diagnostics.failure("selection", exc)
                    # This fail-closed whitelist cannot turn a failed decision
                    # into a fabricated live answer or a write request.
                    from app.companion_information import determine_information_need
                    from app.companion_contracts import CompanionContext
                    need = determine_information_need(CompanionContext(current_message=message, travel_goal=baseline), [])
                    safe = (baseline.target_runtime == "companion" and need.general_knowledge_allowed
                        and not envelope.discussing_place_id and not candidate and not trip_id)
                    unsafe = bool(re.search(r"查|搜|来源|官方|实时|天气|营业|票|预约|路线|多久到|修改|创建|生成|候选|保存|采用|安排|规划|地址|位置|附近|具体门店", message))
                    if safe and not unsafe:
                        decision = CapabilityDecision(intent="direct", reason_code="stable_knowledge")
                    else:
                        raise
                diagnostics.selection = {"intent": decision.intent, "capabilities": decision.capabilities,
                    "reason_code": decision.reason_code, "argument_source": "current_user_scoped_history_or_selected_place"}
                goal = decision_goal(decision, baseline)
                if candidate and decision.candidate_command is None:
                    # An explicit current literal decision uses the same strict
                    # command validator and displayed-version writer; a missing
                    # redundant model wrapper cannot turn adopt into Execution.
                    from app.conversation_candidate.commands import CandidateCommand, validate_command
                    for action in ('adopt', 'discard'):
                        literal = CandidateCommand(action=action, source_quote=message.strip())
                        try:
                            validate_command(literal, message)
                        except ValueError:
                            continue
                        decision = decision.model_copy(update={'intent':'modify', 'candidate_command':literal,
                            'authorization_quote':literal.source_quote})
                        goal = decision_goal(decision, baseline)
                        break
                command = decision.candidate_command if decision.intent in {"create", "modify"} else None
                independent_read=None
                if decision.intent in {'create','modify','execution'} and decision.read_tasks:
                    reader=decision.model_copy(update={'intent':'lookup','candidate_command':None,
                        'planning_draft':None,'creation':None,'authorization_quote':'','memory_updates':[],
                        'saved_intentions':[],'capabilities':list(dict.fromkeys(c for t in decision.read_tasks for c in t.capabilities))})
                    independent_read,read_status=await answer_with_capabilities(settings,reader,message,history,
                        envelope,port,db,trip_id,session_id,message_id,decision_goal(reader,baseline),read_snapshot=read_snapshot)
                    diagnostics.record('independent_read',read_status)
                candidate_conditions_changed = bool(candidate and candidate_snapshot.get("conditions_hash") != conditions_hash(envelope))
                if command and not trip_id and getattr(port, "draft_repository", None) and getattr(port, "owner", None):
                    from app.conversation_candidate.service import build_candidate, publish_candidate, decide_candidate
                    from app.conversation_candidate.commands import validate_command
                    try:
                        validate_command(command, message)
                        if candidate_conditions_changed and command.action != "generate":
                            raise ValueError("旅行条件已经变化，原候选尚未更新，不能保存或只应用部分修改。请按新条件重新生成候选。")
                        if command.action in {"generate", "modify"}:
                            revised, prepared = await build_candidate(command, decision, message, history, envelope,
                                port, candidate, today=captured_at.date(),
                                base_presentation=(candidate_snapshot or {}).get('presentation'))
                            published = await publish_candidate(db, owner=port.owner, session_id=session_id,
                                signature=signature, topic=envelope.topic_id, message_id=message_id, message=message,
                                envelope=envelope, draft=revised, prepared=prepared,
                                old=candidate if command.action == "modify" else None,read_bundle=independent_read)
                            return published, None, {}
                        if not candidate_action(candidate_snapshot, port.owner, envelope.topic_id):
                            raise ValueError("当前没有可采用的候选，请先生成并核对安排。")
                        from app.assistant_routes import CandidateDecisionInput
                        from app.draft_promotion.service import DraftPromotionService
                        from sqlalchemy.ext.asyncio import async_sessionmaker
                        view = candidate_snapshot["presentation"]
                        await db.rollback()
                        writer = DraftPromotionService(port.draft_repository,
                            async_sessionmaker(db.bind, expire_on_commit=False), port.service)
                        result = await decide_candidate(writer, port.owner, session_id, CandidateDecisionInput(
                            protocol_version=2, request_id=message_id, prepared_id=view["prepared_id"],
                            prepared_hash=view["prepared_hash"], presentation_hash=view["presentation_hash"],
                            accept=command.action == "adopt"))
                        return result, None, {}
                    except (ValueError, PromotionError) as exc:
                        text = getattr(exc, "message", str(exc))
                        bundle, status = failure_bundle(envelope, text), "failed"
                        goal = baseline.model_copy(update={"target_runtime": "companion", "mutation_requested": False})
                elif candidate and goal.target_runtime != "companion":
                    # A missing/unsupported edit command cannot create a new Trip
                    # from metadata or silently discard the current candidate.
                    bundle, status = failure_bundle(envelope, "这项调整还没有形成可核对的局部操作，原候选保持不变。请说明要调整的地点和停留时长。"), "complete"
                    goal = baseline.model_copy(update={"target_runtime": "companion", "mutation_requested": False})
                elif decision.intent == "create" and not trip_id and getattr(port, "draft_repository", None) and getattr(port, "owner", None):
                    from app.assistant_operation import approved_tool_decision
                    proposed = approved_tool_decision(decision, message, envelope, today=captured_at.date())
                    text = proposed.reply if proposed.tool == "reply" else "这次还没有生成可核对的地点、时段和路线候选，尚未创建旅行。请重试生成候选，确认保存前可以继续调整。"
                    bundle, status = failure_bundle(envelope, text), "complete"
                    goal = baseline.model_copy(update={"target_runtime": "companion", "mutation_requested": False})
                elif baseline.mutation_requested and goal.target_runtime == 'companion' and (candidate or trip_id) and decision.intent == 'direct':
                    bundle, status = failure_bundle(envelope, '本次修改尚未形成可执行候选；当前候选和正式安排保持原样。请明确要修改的活动与内容。'), 'failed'
                else:
                    bundle = None
                if settings.saved_intentions_enabled:
                    from app.saved_intentions import validate_proposals
                    intentions = validate_proposals(decision.saved_intentions, message, focused_name)
                if intentions and decision.intent == "direct":
                    goal = baseline.model_copy(update={"target_runtime": "companion", "goal_type": "travel_chat", "mutation_requested": False})
                if goal.target_runtime != "companion":
                    from app.assistant_operation import approved_draft, approved_tool_decision
                    draft = approved_draft(decision, message)
                    metadata = {"execution_summary": diagnostics.summary("complete" if read_status in {None,'complete'} else 'partial'),
                        "_semantic_context": envelope.model_dump(mode="json"),
                        "_semantic_history_ids": [str(m.get("id")) for m in history],
                        "_semantic_requested_places": [name for name in decision.names if name in message],
                        "_semantic_read_bundle":independent_read,
                        "_semantic_session_signature": signature}
                    if decision.intent in {"create", "modify"}:
                        tool = approved_tool_decision(decision, message, envelope, today=captured_at.date())
                        metadata["_semantic_tool_decision"] = tool.model_dump(mode="json")
                        if draft:
                            metadata["_semantic_draft"] = draft.model_dump(mode="json")
                        if tool.tool == "create_trip":
                            from app.assistant_service import prepare_action
                            kwargs = {"city_search": city_search} if city_search is not None else {}
                            try:
                                action = await prepare_action(db, tool, None, [], user_text=message, current_message=message, **kwargs)
                            except AssistantToolError as exc:
                                metadata["_semantic_tool_decision"] = {"tool":"reply", "reply":str(exc)}
                            else:
                                action["user_request"] = message
                                if draft:
                                    action["approved_draft"] = draft.model_dump(mode="json")
                                metadata["_semantic_prepared_action"] = action
                    return None, goal, metadata
                from app.assistant_memory import condition_ack
                acknowledgement = condition_ack(envelope, message, changed) if decision.intent == "direct" and decision.response_purpose != "conditions_recall" else None
                if bundle is not None:
                    pass
                elif intentions and decision.intent == "direct":
                    bundle, status = failure_bundle(envelope, "正在保存这项明确打算。"), "complete"
                elif decision.saved_intentions and not settings.saved_intentions_enabled:
                    bundle, status = failure_bundle(envelope, "独立打算保存尚未启用。原话保留在这次对话中，但还没有保存为可独立查看的事项。"), "complete"
                elif acknowledgement:
                    bundle, status = failure_bundle(envelope, acknowledgement), "complete"
                else:
                    bundle, status = await answer_with_capabilities(settings, decision, message, history,
                        envelope, port, db, trip_id, session_id, message_id, goal, read_snapshot=read_snapshot)
                if independent_read:
                    bundle['assistant']+='\n\n同时查询：\n'+independent_read['assistant']
                    if status=='failed' and read_status!='failed':
                        status='partial'
                    for key in ('read_tools','place_cards'):
                        if key in independent_read:
                            bundle[key]=independent_read[key]
                # The legacy conversation projector may return unresolved words
                # such as "哪里"; it is not a geographical identity authority.
                from app.companion_information import explicit_destination
                destination = explicit_destination(message)
                if ("city" not in envelope.conversation_memory.get("withdrawn", {})
                    and not envelope.conversation_memory.get("slots", {}).get("city") and isinstance(destination, str)
                    and 2 <= len(destination) <= 6 and destination in message):
                    from app.assistant_memory import MemoryUpdate
                    envelope, _, _ = apply_memory(envelope, history, message, message_id,
                        [MemoryUpdate(field="city", value=destination, source_quote=destination)])
                    bundle["context"] = envelope.model_dump(mode="json")
                from app.assistant_images import enrich_images, image_requested
                if status != "failed" and (decision.illustrate or image_requested(message)):
                    await enrich_images(settings, bundle, message, envelope)
        except Exception as exc:
            diagnostics.failure("turn", exc)
            # Tool errors do not publish partial unvalidated model output.
            from app.assistant_stream import emit
            emit("reset")
            from app.saved_trip_reads import SavedTripReadStale
            bundle, status = (failure_bundle(envelope, str(exc), read_tools={
                'itinerary_read': {'status': 'needs_retry', 'reason': 'saved_trip_changed'}})
                if isinstance(exc, SavedTripReadStale) else failure_bundle(envelope)), "failed"
            if independent_read:
                bundle['assistant']='本次操作未形成有效修改候选，正式安排未改变。\n\n已执行的独立查询：\n'+independent_read['assistant']
                bundle['read_tools']={**independent_read.get('read_tools',{}),'write_result':{'status':'not_applied'}}
                bundle['place_cards']=independent_read.get('place_cards',[])
                status='partial' if read_status!='failed' else 'failed'
            goal = baseline.model_copy(update={"target_runtime": "companion", "goal_type": "travel_chat", "mutation_requested": False})
        bundle["execution_summary"] = diagnostics.summary(status)
        if status == "failed":
            # Do not leave a streamed partial answer visible after failure.
            from app.assistant_stream import emit
            emit("reset")
        # Reader SELECTs might have opened a transaction before failing.
        await db.rollback()
        fresh = await db.scalar(select(AssistantSession).where(AssistantSession.id == session_id)
            .with_for_update().execution_options(populate_existing=True))
        if fresh is None:
            raise AssistantToolError("对话已清除，请重新打开助手。")
        if any(m.get("id") == str(message_id) for m in fresh.messages):
            return fresh, None, {}
        if snapshot_signature(fresh) != signature:
            await db.rollback()
            raise AssistantToolError("对话已有新的决定，请重新读取当前状态后再查询。")
        pending = fresh.pending_action or {}
        current_city = (envelope.conversation_memory.get("slots", {}).get("city") or {}).get("value")
        if (pending.get("kind") == "itinerary_candidate_v2" and
            (reset_requested(message) or pending.get("topic_id") != envelope.topic_id or
             current_city and current_city.removesuffix("市") != pending.get("presentation", {}).get("city", "").removesuffix("市"))):
            fresh.pending_action = None
        elif pending.get("kind") == "itinerary_candidate_v2" and pending.get("conditions_hash") != conditions_hash(envelope):
            view = {**pending["presentation"], "stage": "stale"}
            fresh.pending_action = {**pending, "presentation": view}
        if intentions and status != "failed" and decision.intent == "direct":
            from app.saved_intentions import persist_proposals
            city = (envelope.conversation_memory.get("slots", {}).get("city") or {}).get("value") or envelope.browsing_city
            saved = await persist_proposals(db, session_id, message_id, intentions, captured_at, city)
            text = "已记下：" + "；".join(f"{i['intended_date'] or '日期未定'} {i['time_period'] or '时间未定'} · {i['place_text']}" for i in saved)
            text += "。具体地点尚待核对；没有创建旅行或调整其他活动。可在我的安排查看或撤销。"
            bundle.update({"assistant": text, "saved_intentions": saved, "intention_write_result": "saved"})
        bundle['memory_update_receipt'] = envelope.conversation_memory.get('latest_receipt', {})
        fresh.messages = [*fresh.messages, {**bundle, "id": str(message_id), "user": message,
            "tool": "reply", "run_id": None, "goal_routing": goal.model_dump(mode="json")}]
        await db.commit()
        return fresh, None, {}
    finally:
        active_turn.reset(token)
