"""Server-owned conversational conditions; user evidence, never write authority."""
import re
from typing import Literal
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = Field(pattern=r"^(city|start_date|duration_days|party_size|budget|preferences|requirements|images)$")
    operation: str = Field(default="set", pattern=r"^(set|add|remove|clear)$")
    value: str = Field(default="", max_length=240)
    replaces: str = Field(default="", max_length=240)
    source_quote: str = Field(min_length=1, max_length=300)
    scope: Literal["personal", "trip", "topic", "destination"] = "personal"


def local_today():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def reset_requested(message):
    return bool(re.search(r"^(?:请|我们|那就|现在|先)?(?:换个话题|换一个话题|重新开始|开始新对话|另一次旅行|另一趟旅行|新的旅行|新的一次旅行|新的一趟旅行)", message.strip()))


def server_memory(envelope):
    value = envelope.conversation_memory
    return value if isinstance(value, dict) and value.get("version") == 1 else {"version": 1, "epoch": "", "slots": {}, "preferences": [], "requirements": []}


def anchored_date(value, today):
    relative = {"今天": 0, "明天": 1, "后天": 2}
    if value in relative:
        return (today + timedelta(days=relative[value])).isoformat()
    week = re.fullmatch(r"(下下|下|本|这)?(?:周|星期)([一二三四五六日天])", value)
    if week:
        weekday = "一二三四五六日".index(week[2].replace("天", "日"))
        offset = {"下下": 2, "下": 1, "本": 0, "这": 0}.get(week[1], 0)
        result = today - timedelta(days=today.weekday()) + timedelta(days=offset * 7 + weekday)
        if not week[1] and result < today:
            result += timedelta(days=7)
        return result.isoformat()
    try:
        if re.fullmatch(r"20\d{2}-\d{1,2}-\d{1,2}", value):
            return date.fromisoformat(value).isoformat()
        match = re.fullmatch(r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})[日号]?", value)
        if match:
            chosen = date(int(match[1] or today.year), int(match[2]), int(match[3]))
            if not match[1] and chosen < today:
                chosen = chosen.replace(year=today.year + 1)
            return chosen.isoformat()
    except ValueError:
        pass
    return None


def _quoted_scalar(key, value, quote, today):
    """Normalize only a single explicit quantity/date equal to the proposal."""
    if key == "start_date":
        tokens = re.findall(r"今天|明天|后天|20\d{2}-\d{1,2}-\d{1,2}|(?:20\d{2}年)?\d{1,2}月\d{1,2}[日号]?|(?:下下|下|本|这)?(?:周|星期)[一二三四五六日天]", quote)
        dates = [anchored_date(token, today) for token in tokens]
        proposed = anchored_date(value, today)
        return proposed if len(dates) == 1 and proposed and dates[0] == proposed else None
    from app.travel_language import chinese_number
    numeral = r"[一二三四五六七八九十两\d]+"
    unit = r"天" if key == "duration_days" else r"(?:个?人|位)"
    proposed = re.fullmatch(rf"({numeral})\s*(?:{unit})?", value)
    tokens = re.findall(rf"({numeral})\s*{unit}", quote)
    # Mixed adult/child groups require a semantic sum, not a verified scalar.
    if key == "party_size" and re.search(r"成人|儿童|孩子|小孩", quote):
        return None
    if not proposed or len(tokens) != 1:
        return None
    number = chinese_number(proposed[1])
    return number if 1 <= number <= (31 if key == "duration_days" else 100) and number == chinese_number(tokens[0]) else None


def literal_conditions(message):
    """Exact date/duration slot answers also work in the existing planning handoff."""
    if re.search(r"如果|假如|假设|要是|[“”「」\"?？]|是否|吗|几天|合适|介绍|解释|朋友|听说|他|她|取消出发|不出发", message):
        return []
    updates = []
    if re.search(r"我(?:们)?.{0,8}(?:去|到)|改去|目的地(?:改为|改成|为|是)", message):
        from app.companion_information import explicit_destination
        city = explicit_destination(message)
        if city and city in message:
            updates.append(MemoryUpdate(field="city", value=city, source_quote=city, scope="trip"))
    date_token = r"今天|明天|后天|20\d{2}-\d{2}-\d{2}|(?:20\d{2}年)?\d{1,2}月\d{1,2}[日号]|(?:下下|下|本|这)?(?:周|星期)[一二三四五六日天]"
    match = re.search(rf"({date_token})(?:\s*(?:开始|出发|去))|(?:出发(?:日期)?(?:改为|改成|为|是)?|改为|改成)\s*({date_token})", message)
    if match:
        updates.append(MemoryUpdate(field="start_date", value=match[1] or match[2], source_quote=match[0], scope="trip"))
    duration = re.search(r"(?:游玩|玩|待|改为|改成|那就)([一二三四五六七八九十两\d]+天)", message)
    if duration:
        updates.append(MemoryUpdate(field="duration_days", value=duration[1], source_quote=duration[0], scope="trip"))
    # Exact scalar withdrawal must survive a selector omitting a patch, just as
    # literal departure/duration answers do. The noun alone ("目的地") is not
    # an affirmative city declaration. These statements confer no write rights.
    fields = {"目的地": "city", "出发日期": "start_date", "日期": "start_date", "预算": "budget", "同行人数": "party_size"}
    labels = "|".join(fields)
    for match in re.finditer(rf"(?:取消|清除|忘掉)(?:这次的?|原来的?)?({labels})|({labels})(?:也|都)?(?:先|暂时|还)?(?:不定|未定|待定|没定|不确定)", message):
        updates.append(MemoryUpdate(field=fields[match[1] or match[2]], operation="clear", source_quote=match[0], scope="trip"))
    # High-precision personal declarations must not disappear when the single
    # semantic selector omits a memory patch beside dates/duration. These are
    # literal user data only; apply_memory still checks provenance and scope.
    for clause in re.split(r"[，,。；;!?！？]", message):
        clause = clause.strip()
        if re.search(r"不是不吃辣|不再不吃辣|不用不吃辣|不必不吃辣|不用吃素|不再吃素", clause):
            continue
        match = re.fullmatch(r"(?:我(?:们)?(?:都)?|这次|全程|完全|严格)?\s*(不吃辣|不能吃辣|吃不了辣|吃素|少走路|慢慢逛|别太赶)", clause)
        if match:
            updates.append(MemoryUpdate(field="preferences", operation="add", value=match[1], source_quote=clause,
                                        scope="trip" if re.match(r"这次|全程", clause) else "personal"))
    return updates


def apply_memory(envelope, history, message, message_id, updates=(), *, today=None):
    """Only exact current-user quotes can update persisted conditions.

    A city correction keeps personal conditions, but drops old place focus.
    A new conversation/task resets all local conditions and its prompt history.
    """
    from copy import deepcopy
    memory = deepcopy(server_memory(envelope))
    reset = reset_requested(message) and memory.get("epoch") != str(message_id)
    if reset:
        # A different journey within this chat can reuse explicitly personal
        # preferences. A new conversation/topic or "重新开始" clears everything.
        new_journey = bool(re.match(r"^(?:请|我们|那就|现在|先)?(?:另一次旅行|另一趟旅行|新的旅行|新的一次旅行|新的一趟旅行)", message.strip()))
        # Pre-B selectors labelled temporary trip constraints "personal" too.
        # Those legacy labels cannot acquire new cross-journey persistence.
        personal = {key: [item for item in memory[key] if item.get("scope") == "personal" and item.get("scope_version") == 2] if new_journey else []
                    for key in ("preferences", "requirements")}
        memory = {"version": 1, "epoch": str(message_id), "slots": {}, **personal, "detached_trip": True}
        history = []
        envelope = envelope.model_copy(update={"browsing_city": None, "discussing_place_id": None,
            "discussing_place_ids": [], "discovery_context": None, "requirements": None, "requirement_records": [], "read_trip_id": None,
            "read_draft_id": None, "read_draft_version": None, "action_target": None, "route_request": None})
    original_city = memory["slots"].get("city", {}).get("value") or envelope.browsing_city
    accepted = []
    from app.requirement_language import current_user_evidence_reason
    diagnostics = []
    for update in updates:
        quote, value = update.source_quote, update.value.strip()
        reason = current_user_evidence_reason(message, quote)
        if reason:
            diagnostics.append({"field": update.field, "reason": reason, "source_quote": quote, "message_id": str(message_id)})
            continue
        prefix = message[:message.find(quote)]
        key, operation = update.field, update.operation
        if key == "city" and value in {"哪里", "哪儿", "哪个城市", "什么城市", "某地", "未知", "未定"}:
            continue
        if key in {"preferences", "requirements"} and (operation == "remove" or update.replaces) and not re.search(r"取消|不再|不看|不要|不喜欢|不想|改|换|可以|现在|清除|撤销|忘掉", quote):
            continue
        normalized = value
        if operation not in {"clear", "remove"}:
            if key in {"duration_days", "party_size", "start_date"}:
                normalized = _quoted_scalar(key, value, quote, today or local_today())
                if normalized is None:
                    diagnostics.append({"field": key, "reason": "unverified_date_value" if key == "start_date" else "unverified_numeric_value", "source_quote": quote, "message_id": str(message_id)})
                    continue
            elif key in {"preferences", "requirements"}:
                # A literal fragment may still erase negation/subject/scope.
                # Only removing a plain first-person declaration prefix is safe.
                safe_literal = value and value in quote and re.fullmatch(r"(?:我(?:们)?(?:一直|都)?|这次)?\s*" + re.escape(value), quote)
                if not safe_literal:
                    normalized = value = quote
                    diagnostics.append({"field": key, "reason": "preserved_literal_condition", "source_quote": quote, "message_id": str(message_id)})
            elif not value or value not in quote:
                diagnostics.append({"field": key, "reason": "value_not_in_source", "source_quote": quote, "message_id": str(message_id)})
                continue
        if key == "city" and operation not in {"clear", "remove"} and re.search(r"不去|别去|不要去|不想去|取消去", re.split(r"[，。；!?！？]", prefix)[-1] + quote):
            continue
        if operation == "clear" and not re.search(r"取消|不限|不设|清除|忘掉|不再|不要|无需|不用|待定|(?:先|还|也)?不定|未定|没(?:有)?定|不确定", quote):
            continue
        evidence = {"value": normalized, "source_quote": quote, "message_id": str(message_id), "scope": update.scope, "scope_version": 2}
        withdrawn = memory.setdefault("withdrawn", {})
        withdrawal_key = key + (":" + (update.replaces or value) if key in {"preferences", "requirements"} and operation != "clear" else "")
        if operation in {"clear", "remove"}:
            withdrawn[withdrawal_key] = {"source_quote": quote, "message_id": str(message_id), "state": "unknown" if key not in {"preferences", "requirements"} else "withdrawn"}
        else:
            withdrawn.pop(key, None)
            withdrawn.pop(key + ":" + value, None)
            if update.replaces:
                withdrawn[key + ":" + update.replaces] = {"source_quote": quote, "message_id": str(message_id), "state": "superseded"}
        if key in {"preferences", "requirements"}:
            items = memory[key]
            if operation == "clear":
                items = []
            else:
                remove = update.replaces or (value if operation == "remove" else "")
                items = [item for item in items if item["value"] not in {remove, value}]
                if operation != "remove":
                    items.append(evidence)
            memory[key] = items[-20:]
        elif operation in {"clear", "remove"}:
            memory["slots"].pop(key, None)
        else:
            memory["slots"][key] = evidence
        accepted.append(key)
    city = memory["slots"].get("city", {}).get("value")
    # Latest-turn validation metadata is data, never an effective condition.
    memory["diagnostics"] = diagnostics[-20:]
    memory["withdrawn"] = dict(list(memory.get("withdrawn", {}).items())[-40:])
    changes = {"conversation_memory": memory}
    # Scalar withdrawal must reach the older typed projection as well. It never
    # edits a saved Trip; these are only the current conversation's conditions.
    if envelope.requirements and any(k in accepted and k not in memory["slots"] for k in ("budget", "party_size")):
        changes["requirements"] = envelope.requirements.model_copy(update={
            **({"budget_fen": None} if "budget" in accepted and "budget" not in memory["slots"] else {}),
            **({"party_size": None} if "party_size" in accepted and "party_size" not in memory["slots"] else {})})
    if city:
        changes["browsing_city"] = city
    cleared_city = "city" in accepted and not city
    if cleared_city or (city and original_city and city.removesuffix("市") != original_city.removesuffix("市")):
        # Old recommendation IDs, POI focus and local constraints cannot cross cities.
        history = []
        memory["epoch"] = str(message_id)
        memory["detached_trip"] = True
        for key in ("preferences", "requirements"):
            memory[key] = [r for r in memory[key] if r.get("scope", "personal") not in {"destination", "topic"}]
        memory["slots"] = {key: item for key, item in memory["slots"].items()
                           if key == "city" or item.get("scope", "personal") not in {"destination", "topic"}}
        changes.update(discussing_place_id=None, discussing_place_ids=[], discovery_context=None,
            requirement_records=[], requirements=None, read_trip_id=None, read_draft_id=None, read_draft_version=None,
            action_target=None, route_request=None)
        if cleared_city:
            changes["browsing_city"] = None
    return envelope.model_copy(update=changes), history, accepted


def memory_prompt(envelope):
    memory = server_memory(envelope)
    return {"slots": memory["slots"], "preferences": memory["preferences"], "requirements": memory["requirements"],
            "withdrawn": memory.get("withdrawn", {}), "diagnostics": memory.get("diagnostics", [])}


def bootstrap_memory(envelope, history):
    """Conservative upgrade of older server messages, never assistant assertions.

    Old relative dates without their observation time stay unresolved instead of
    silently moving the user's departure to tomorrow again after deployment.
    """
    if envelope.conversation_memory.get("version") == 1:
        return envelope
    for turn in history:
        text = turn.get("user", "")
        if re.search(r"如果|假如|假设|要是|[“”「」\"]", text):
            continue
        updates = []
        if re.search(r"(?:我|我们|这次).{0,5}(?:去|到)", text):
            from app.companion_information import explicit_destination
            city = explicit_destination(text)
            if city and city in text:
                updates.append(MemoryUpdate(field="city", value=city, source_quote=text[:300]))
        absolute = re.search(r"20\d{2}-\d{2}-\d{2}", text)
        if absolute and re.search(r"出发|去|开始", text):
            updates.append(MemoryUpdate(field="start_date", value=absolute[0], source_quote=text[:300]))
        duration = re.search(r"(?:玩|游玩|待|改成|改为|那就)([一二三四五六七八九十两\d]+天)", text)
        if duration and not re.search(r"几天|合适|够吗|是否", text):
            updates.append(MemoryUpdate(field="duration_days", value=duration[1], source_quote=duration[0]))
        for clause in re.split(r"[，。；!?！？]", text):
            if re.search(r"我(?:们)?(?:不?喜欢|偏好)|不吃辣|吃素|少走路|慢慢逛", clause):
                literal = clause.strip()[:240]
                if literal:
                    updates.append(MemoryUpdate(field="preferences", operation="add", value=literal, source_quote=literal))
        # Historical messages have no verified scope evidence. Keep recovered
        # conditions useful within this journey without upgrading them into
        # durable personal preferences under the new selector contract.
        updates = [update.model_copy(update={"scope": "trip"}) for update in updates]
        envelope, _, _ = apply_memory(envelope, [], text, turn.get("id", "legacy"), updates)
    return envelope


def condition_ack(envelope, message, changed):
    if not changed or re.search(r"[?？]|吗|什么|哪些|如何|怎样|怎么|介绍|了解|想知道|聊|推荐|区别|解释|查询|搜索|看看|说说|建议|是否|能不能|列出|罗列|景点|攻略|展开|详细|告诉|给我|帮我", message):
        return None
    memory = server_memory(envelope)
    names = {"city": "目的地", "start_date": "出发日期", "duration_days": "游玩天数", "party_size": "同行人数", "budget": "预算", "images": "配图偏好"}
    parts = []
    for key in dict.fromkeys(changed):
        if key in {"preferences", "requirements"}:
            values = "、".join(i["value"] for i in memory[key])
            parts.append(("偏好" if key == "preferences" else "要求") + ("：" + values if values else "已清除"))
        else:
            value = memory["slots"].get(key, {}).get("value")
            parts.append(names[key] + ("：" + str(value) if value is not None else "已清除"))
    return "已更新这次聊天的条件：" + "；".join(parts) + "。"
