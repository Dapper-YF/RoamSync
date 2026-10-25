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
    subject: str = Field(default='', max_length=50)


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


def _affirmative_scalar_token(message, start, end):
    """A literal quantity is not an assertion when its clause negates it."""
    punctuation = r"[，,。；;!?！？\n]"
    correction = r"改(?:为|成|玩|到|(?=[一二三四五六七八九十两\d]|$))|而是"
    prefix = re.split(punctuation, message[:start])[-1]
    correction_end = 0
    for marker in re.finditer(correction, prefix):
        # A negated correction is not an affirmative clause boundary either.
        if not re.search(r"(?:不|没|别|非)(?:是|有|要|想|再|会|能)?\s*$", prefix[:marker.start()]):
            correction_end = marker.end()
    prefix = prefix[correction_end:]
    suffix = re.split(punctuation + "|" + correction, message[end:])[0]
    return not (re.search(r"不|没|别|取消|撤销", prefix)
                or re.match(r"\s*(?:不(?:是|要|去|出发|开始|玩|待|同行|出游)|没|取消|撤销)", suffix))


def _quoted_scalar(key, value, quote, today, message):
    """Normalize a single affirmative quoted quantity/date equal to proposal."""
    quote_start = message.find(quote)
    if key == "start_date":
        tokens = re.finditer(r"今天|明天|后天|20\d{2}-\d{1,2}-\d{1,2}|(?:20\d{2}年)?\d{1,2}月\d{1,2}[日号]?|(?:下下|下|本|这)?(?:周|星期)[一二三四五六日天]", quote)
        dates = [anchored_date(token[0], today) for token in tokens
                 if _affirmative_scalar_token(message, quote_start + token.start(), quote_start + token.end())]
        proposed = anchored_date(value, today)
        return proposed if len(dates) == 1 and proposed and dates[0] == proposed else None
    from app.travel_language import chinese_number
    if key == 'party_size' and (value in {'1', '一', '一个人', '1人'} or value and value in quote):
        solo = re.search(r'(?:就|只剩|只|剩下)?我(?:(?:自己|独自|单独)(?:一个人)?|一个人)(?:去|出发|旅行|玩)', quote)
        if solo and _affirmative_scalar_token(message, quote_start + solo.start(), quote_start + solo.end()):
            return 1
    if key == 'party_size':
        # Enumerated individuals are count evidence even without a numeric
        # token. Groups/plurals and mixed adult/child quantities stay unknown.
        group = re.fullmatch(r'(.+?)(?:一起|一同)(?:去|出发|旅行)', quote.strip())
        members = re.split(r'和|与|跟|、', group[1]) if group else []
        if (2 <= len(members) <= 8 and '我' in members and len(set(members)) == len(members)
            and all(re.fullmatch(r'[\u4e00-\u9fff]{1,8}', m) and not re.search(
                r'们|家人|全家|一家|同事|同学|大家|几|[一二三四五六七八九十两]',m) for m in members)
            and (value == quote or value in {str(len(members)), str(len(members))+'人'})):
            return len(members)
    numeral = r"[一二三四五六七八九十两\d]+"
    unit = r"(?:天|日)" if key == "duration_days" else r"(?:个?人|位)"
    proposed = re.fullmatch(rf"({numeral})\s*(?:{unit})?", value)
    if proposed is None and key == 'party_size' and value in quote:
        proposed_tokens = re.findall(rf'{numeral}\s*{unit}', value)
        if len(proposed_tokens) == 1:
            proposed = re.fullmatch(rf"({numeral})\s*{unit}", proposed_tokens[0])
    tokens = [token[1] for token in re.finditer(rf"({numeral})\s*{unit}", quote)
              if not (key=='duration_days' and re.search(r'[年月./-]\s*$',quote[:token.start()]))
              if _affirmative_scalar_token(message, quote_start + token.start(), quote_start + token.end())]
    # Mixed adult/child groups require a semantic sum, not a verified scalar.
    if key == "party_size" and re.search(r"成人|儿童|孩子|小孩", quote):
        return None
    if not proposed or len(tokens) != 1:
        return None
    number = chinese_number(proposed[1])
    return number if 1 <= number <= (31 if key == "duration_days" else 100) and number == chinese_number(tokens[0]) else None


def literal_conditions(message):
    """Exact date/duration slot answers also work in the existing planning handoff."""
    # A verified single-person declaration does not depend on the selector's
    # optional memory patch or on another clause mentioning a companion.
    from app.requirement_language import current_user_evidence_reason
    solo_updates=[]
    for clause in re.split(r'[，,。；;!?！？]',message):
        if (re.fullmatch(r'(?:这次|这趟)?(?:就|只剩|只|剩下)?我(?:(?:自己|独自|单独)(?:一个人)?|一个人)(?:去|出发|旅行|玩)',clause.strip())
            and not current_user_evidence_reason(message,clause.strip())):
            solo_updates.append(MemoryUpdate(field='party_size',value='1',source_quote=clause.strip(),scope='trip'))
        from app.travel_language import trip_duration
        count=trip_duration(clause)
        if (count and re.search(r'候选|行程|安排|游玩|玩|旅行',clause)
            and _quoted_scalar('duration_days',str(count),clause,local_today(),message)==count
            and not current_user_evidence_reason(message,clause)
            and not re.search(r'是否|吗|合适|够不够|[?？]',message)):
            solo_updates.append(MemoryUpdate(field='duration_days',value=str(count),source_quote=clause.strip(),scope='trip'))
    if re.search(r"如果|假如|假设|要是|[“”「」\"?？]|是否|吗|几天|合适|介绍|解释|朋友|听说|他|她|取消出发|不出发", message):
        return solo_updates
    updates = list(solo_updates)
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
    records = envelope.requirement_records
    from app.requirement_language import current_user_evidence_reason
    # Reuse the same literal departure predicate as removal validation. The
    # event acts only on already-owned trip conditions for that exact subject;
    # it cannot revoke another person's, personal or global preference.
    linked=[]
    for clause in re.split(r'[，,。；;!?！？]',message):
        departed=_departed_subjects(clause.strip())
        if not departed or current_user_evidence_reason(message,clause.strip()):
            continue
        for field in ('preferences','requirements'):
            for item in memory[field]:
                if item.get('subject') in departed and item.get('scope')=='trip':
                    linked.append(MemoryUpdate(field=field,operation='remove',value=item['value'],
                        source_quote=clause.strip(),subject=item['subject'],scope='trip'))
    updates=[*linked,*updates]
    diagnostics = []
    previous_receipt = memory.get('latest_receipt', {})
    receipts = list(previous_receipt.get('updates', [])) if previous_receipt.get('message_id') == str(message_id) else []
    for update in updates:
        quote, value = update.source_quote, update.value.strip()
        receipt = {'field': update.field, 'operation': update.operation, 'value': value,
            'subject': update.subject, 'scope': 'trip' if update.subject else update.scope,
            'source_quote': quote, 'status': 'rejected', 'reason': 'source_or_scope_not_verified'}
        receipts = [r for r in receipts if any(r.get(k) != receipt.get(k) for k in
            ('field', 'operation', 'value', 'subject', 'scope', 'source_quote'))]
        receipts.append(receipt)
        reason = current_user_evidence_reason(message, quote)
        if reason:
            receipt['reason'] = reason
            diagnostics.append({"field": update.field, "reason": reason, "source_quote": quote, "message_id": str(message_id)})
            continue
        prefix = message[:message.find(quote)]
        key, operation = update.field, update.operation
        from app.requirement_language import is_context_only_statement
        if key in {'preferences','requirements'} and operation not in {'remove','clear'} and is_context_only_statement(quote):
            receipt['reason']='workflow_not_travel_condition'
            continue
        if key == "city" and value in {"哪里", "哪儿", "哪个城市", "什么城市", "某地", "未知", "未定"}:
            continue
        departed_subjects = _departed_subjects(quote)
        subject_withdrawal = bool(update.subject and update.subject in departed_subjects)
        if update.subject in {'我', '本人', '我们', '用户'}:
            continue
        if update.subject and not quote.startswith(update.subject) and operation not in {'remove', 'clear'}:
            continue
        if key in {"preferences", "requirements"} and (operation == "remove" or update.replaces) and not (subject_withdrawal or re.search(r"取消|不再|不看|不要|不喜欢|不想|改|换|可以|现在|清除|撤销|撤掉|忘掉", quote)):
            continue
        normalized = value
        if operation not in {"clear", "remove"}:
            if key in {"duration_days", "party_size", "start_date"}:
                normalized = _quoted_scalar(key, value, quote, today or local_today(), message)
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
        if operation == "clear" and not re.search(r"取消|撤销|撤掉|不限|不设|清除|忘掉|不再|不要|无需|不用|待定|(?:先|还|也)?不定|未定|没(?:有)?定|不确定", quote):
            continue
        evidence = {"value": normalized, "source_quote": quote, "message_id": str(message_id),
            "scope": 'trip' if update.subject else update.scope, "scope_version": 2,
            **({'subject': update.subject} if update.subject else {})}
        if key in {'preferences', 'requirements'} and operation == 'remove':
            remove = update.replaces or value
            matching = [item for item in memory[key] if item['value'] == remove and
                item.get('scope', 'personal') == ('trip' if update.subject else update.scope) and
                (item.get('subject', '') == update.subject or update.subject and
                 not item.get('subject') and item.get('source_quote', '').startswith(update.subject))]
            if not matching:
                prior_key=key+':'+remove+(':'+update.subject+':trip' if update.subject else '')
                if memory.get('withdrawn',{}).get(prior_key,{}).get('state')=='withdrawn':
                    receipt.update(status='applied',reason='already_withdrawn',effective_value=[i['value'] for i in memory[key]])
                    continue
                receipt['reason'] = 'matching_condition_not_found'
                continue
        withdrawn = memory.setdefault("withdrawn", {})
        withdrawal_key = key + (":" + (update.replaces or value) if key in {"preferences", "requirements"} and operation != "clear" else "")
        if update.subject:
            withdrawal_key += ':' + update.subject + ':trip'
        if operation in {"clear", "remove"}:
            withdrawn[withdrawal_key] = {"source_quote": quote, "message_id": str(message_id), "state": "unknown" if key not in {"preferences", "requirements"} else "withdrawn"}
        else:
            withdrawn.pop(key, None)
            withdrawn.pop(key + ":" + value, None)
            if update.replaces:
                withdrawn[key + ":" + update.replaces] = {"source_quote": quote, "message_id": str(message_id), "state": "superseded"}
        if key in {"preferences", "requirements"}:
            items = memory[key]
            removed_items = [item for item in items if (
                item.get('subject', '') == update.subject
                and item.get('scope', 'personal') == evidence['scope'])] if operation == 'clear' else (
                matching if operation == 'remove' else [item for item in items if update.replaces
                    and item['value'] == update.replaces and item.get('subject', '') == update.subject
                    and item.get('scope', 'personal') == evidence['scope']])
            # Both stores already contain provenance. Revoke only atoms from
            # the same source message and exact condition clause, never other
            # clauses sharing that message or a durable/global requirement.
            from app.requirements import valid_records, revoke_requirement
            for prior in removed_items:
                for record in valid_records(records):
                    if (record['status'] == 'active' and record['source']['ref'] == prior.get('message_id')
                        and record['scope']['kind'] != 'global_preference'
                        and record['text'].strip() == prior.get('source_quote', '').strip()
                        and (not update.subject or record['text'].startswith(update.subject))):
                        records = revoke_requirement(records, record['id'], source_ref=str(message_id))
            if operation == "clear":
                items = [item for item in items if not (
                    item.get('subject', '') == update.subject and
                    item.get('scope', 'personal') == ('trip' if update.subject else update.scope))]
            else:
                remove = update.replaces or (value if operation == "remove" else "")
                items = [item for item in items if item["value"] not in {remove, value}
                         or (item not in matching if operation == 'remove' else
                             item.get('subject', '') != update.subject or item.get('scope', 'personal') != evidence['scope'])]
                if operation != "remove":
                    items.append(evidence)
            memory[key] = items[-20:]
        elif operation in {"clear", "remove"}:
            memory["slots"].pop(key, None)
        else:
            memory["slots"][key] = evidence
        accepted.append(key)
        receipt.update(status='applied', reason='validated', effective_value=normalized if key not in {'preferences', 'requirements'} else
            [i['value'] for i in memory[key]])
    city = memory["slots"].get("city", {}).get("value")
    # Latest-turn validation metadata is data, never an effective condition.
    memory["diagnostics"] = diagnostics[-20:]
    memory["withdrawn"] = dict(list(memory.get("withdrawn", {}).items())[-40:])
    changes = {"conversation_memory": memory, "requirement_records": records}
    # Scalar withdrawal must reach the older typed projection as well. It never
    # edits a saved Trip; these are only the current conversation's conditions.
    if envelope.requirements and any(k in accepted for k in ("budget", "party_size")):
        changes["requirements"] = envelope.requirements.model_copy(update={
            **({"budget_fen": None} if "budget" in accepted and "budget" not in memory["slots"] else {}),
            **({"party_size": memory['slots'].get('party_size', {}).get('value')} if 'party_size' in accepted else {})})
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
    memory['latest_receipt'] = {'version': 1, 'message_id': str(message_id), 'updates': receipts[-32:],
        'effective_slots': deepcopy(memory['slots']), 'effective_preferences': deepcopy(memory['preferences']),
        'effective_requirements': deepcopy(memory['requirements'])}
    return envelope.model_copy(update=changes), history, accepted


def _departed_subjects(quote):
    departure=re.fullmatch(r'(.+?)(?:这次)?(?:都|也)?(?:不去了|不来了|不同行了?|退出了?|不参加(?:这次)?(?:旅行|行程)了?)[。！!\s]*',quote)
    return re.split(r'和|与|及|、',departure[1]) if departure else []


def memory_prompt(envelope):
    memory = server_memory(envelope)
    return {"slots": memory["slots"], "preferences": memory["preferences"], "requirements": memory["requirements"],
            "withdrawn": memory.get("withdrawn", {}), "diagnostics": memory.get("diagnostics", [])}


def recall_conditions(envelope):
    """Render current server-owned conditions without semantic compression.

    Browsing context, history, rejected proposals and external places provide no
    additional confirmed condition. The approved semantic decision selects when
    this renderer is used; it never classifies the question or calls a model.
    """
    memory = server_memory(envelope)
    slots, withdrawn = memory["slots"], memory.get("withdrawn", {})
    lines = []
    for key, label, unit in (("city", "目的地", ""), ("start_date", "出发日期", ""),
                            ("duration_days", "游玩天数", "天"), ("party_size", "同行人数", "人"),
                            ("budget", "预算", "")):
        value = slots.get(key, {}).get("value")
        if value is not None and value != "":
            rendered = str(value) + (unit if isinstance(value, int) and not isinstance(value, bool) else "")
        elif key in withdrawn:
            rendered = "待定" if key == "start_date" else "已撤销"
        else:
            rendered = "未确定"
        lines.append(label + "：" + rendered)
    for key, label in (("preferences", "偏好"), ("requirements", "要求")):
        literal = [item.get("source_quote") or item.get("value") for item in memory[key]]
        literal = [value for value in literal if isinstance(value, str) and value]
        removed = any(k == key or k.startswith(key + ':') for k in withdrawn)
        lines.append(label + "：" + ("；".join(literal) if literal else "已撤销" if removed else "未确定"))
    rejected = [r for r in memory.get('latest_receipt', {}).get('updates', []) if r['status'] == 'rejected']
    if rejected:
        lines.append('本次未应用：'+'；'.join(dict.fromkeys(r['field']+'（'+r['reason']+'）' for r in rejected))+'，以上为实际保留值。')
    return "这次聊天当前的有效条件：\n" + "\n".join(lines)


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
    receipt = server_memory(envelope).get('latest_receipt', {})
    rejected = [r for r in receipt.get('updates', []) if r['status'] == 'rejected']
    if (not changed and not rejected) or re.search(r"[?？]|吗|什么|哪些|如何|怎样|怎么|介绍|了解|想知道|聊|推荐|区别|解释|查询|搜索|看看|说说|建议|是否|能不能|列出|罗列|景点|攻略|展开|详细|告诉|给我|帮我", message):
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
    failed = '；'.join(dict.fromkeys(r['field'] for r in rejected))
    return ('已更新这次聊天的条件：' + '；'.join(parts) + '。' if parts else '') + (
        '未应用的字段：' + failed + '，原有值保留，请明确说明对应条件。' if failed else '')
