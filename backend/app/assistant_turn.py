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
from app.database import AssistantSession, Trip
from app.travel_goal_router import route_travel_goal


async def semantic_turn(db, session_id, message, message_id, incoming, port, settings, selector=None):
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
    if trip_id:
        trip = await db.get(Trip, trip_id)
        if trip is None:
            raise AssistantToolError("旅行不存在，请刷新后重试。")
        summary = {"destination": trip.destination, "title": trip.title, "version": trip.version}
    envelope = capture_effective_requirements(capture_requirements(envelope, message), message, message_id=message_id)
    baseline = route_travel_goal(message, history[-12:], pending_action=row.pending_action)
    await db.commit()
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
                        trip_id, summary = None, None
                    # The corrected conversational city wins over an older UI city.
                    city = (envelope.conversation_memory.get("slots", {}).get("city") or {}).get("value")
                    if city and decision.city and decision.city not in message:
                        decision = decision.model_copy(update={"city": city})
                    decision = validate_decision(decision, message, history, envelope,
                        [*[c["place"] for m in history[-3:] for c in m.get("place_cards", [])],
                         *([{"city": summary["destination"]}] if summary else [])])
                except Exception as exc:
                    diagnostics.failure("selection", exc)
                    # This fail-closed whitelist cannot turn a failed decision
                    # into a fabricated live answer or a write request.
                    from app.companion_information import determine_information_need
                    from app.companion_contracts import CompanionContext
                    need = determine_information_need(CompanionContext(current_message=message, travel_goal=baseline), [])
                    safe = baseline.target_runtime == "companion" and need.general_knowledge_allowed and not envelope.discussing_place_id
                    unsafe = bool(re.search(r"查|搜|来源|官方|实时|天气|营业|票|预约|路线|多久到|修改|创建|安排|规划|地址|位置|附近|具体门店", message))
                    if safe and not unsafe:
                        decision = CapabilityDecision(intent="direct", reason_code="stable_knowledge")
                    else:
                        raise
                diagnostics.selection = {"intent": decision.intent, "capabilities": decision.capabilities,
                    "reason_code": decision.reason_code, "argument_source": "current_user_scoped_history_or_selected_place"}
                goal = decision_goal(decision, baseline)
                if settings.saved_intentions_enabled:
                    from app.saved_intentions import validate_proposals
                    intentions = validate_proposals(decision.saved_intentions, message, focused_name)
                if intentions and decision.intent == "direct":
                    goal = baseline.model_copy(update={"target_runtime": "companion", "goal_type": "travel_chat", "mutation_requested": False})
                if goal.target_runtime != "companion":
                    return None, goal, {"execution_summary": diagnostics.summary("complete"), "_semantic_context": envelope.model_dump(mode="json"), "_semantic_history_ids": [str(m.get("id")) for m in history], "_semantic_requested_places": [name for name in decision.names if name in message]}
                from app.assistant_memory import condition_ack
                acknowledgement = condition_ack(envelope, message, changed) if decision.intent == "direct" and decision.response_purpose == "conditions_only" else None
                if intentions and decision.intent == "direct":
                    bundle, status = failure_bundle(envelope, "正在保存这项明确打算。"), "complete"
                elif decision.saved_intentions and not settings.saved_intentions_enabled:
                    bundle, status = failure_bundle(envelope, "独立打算保存尚未启用。原话保留在这次对话中，但还没有保存为可独立查看的事项。"), "complete"
                elif acknowledgement:
                    bundle, status = failure_bundle(envelope, acknowledgement), "complete"
                else:
                    bundle, status = await answer_with_capabilities(settings, decision, message, history,
                        envelope, port, db, trip_id, session_id, message_id, goal)
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
                if status != "failed" and decision.illustrate:
                    from app.assistant_images import enrich_images
                    await enrich_images(settings, bundle, message, envelope)
        except Exception as exc:
            diagnostics.failure("turn", exc)
            # Tool errors do not publish partial unvalidated model output.
            from app.assistant_stream import emit
            emit("reset")
            bundle, status = failure_bundle(envelope), "failed"
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
        if intentions and status != "failed" and decision.intent == "direct":
            from app.saved_intentions import persist_proposals
            city = (envelope.conversation_memory.get("slots", {}).get("city") or {}).get("value") or envelope.browsing_city
            saved = await persist_proposals(db, session_id, message_id, intentions, captured_at, city)
            text = "已记下：" + "；".join(f"{i['intended_date'] or '日期未定'} {i['time_period'] or '时间未定'} · {i['place_text']}" for i in saved)
            text += "。具体地点尚待核对；没有创建旅行或调整其他活动。可在我的安排查看或撤销。"
            bundle.update({"assistant": text, "saved_intentions": saved, "intention_write_result": "saved"})
        fresh.messages = [*fresh.messages, {**bundle, "id": str(message_id), "user": message,
            "tool": "reply", "run_id": None, "goal_routing": goal.model_dump(mode="json")}]
        await db.commit()
        return fresh, None, {}
    finally:
        active_turn.reset(token)
