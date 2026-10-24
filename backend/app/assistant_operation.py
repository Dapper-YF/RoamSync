"""Translate the one source-bound semantic decision into existing operations.

No model, Session, generated IDs or write authority lives in this module.
"""
import re
from datetime import date, time, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.flexible_creation import CreationChoice
from app.schemas import SemanticIntentDraft


class CreationItemProposal(BaseModel):
    """Extraction may be incomplete; the existing writer owns precision."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["selected", "optional", "free_window", "appointment", "blank_day"]
    label: str = Field(min_length=1, max_length=160)
    origin: Literal["user_explicit", "ai_suggestion"] = "user_explicit"
    source_quote: str = Field(default="", max_length=600)
    day_date: date | None = None
    start: time | None = None
    end: time | None = None


class CreationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination: str = Field(default="", max_length=120)
    start_date: date | None = None
    end_date: date | None = None
    total_budget_fen: int | None = Field(default=None, gt=0, le=100_000_000)
    flexible: bool = False
    choices: list[CreationItemProposal] = Field(default_factory=list, max_length=30)

    @model_validator(mode="before")
    @classmethod
    def normalize_literal_whole_day(cls, value):
        if not isinstance(value, dict):
            return value
        from app.flexible_creation import whole_day_quote
        result = dict(value)
        result["choices"] = []
        for item in value.get("choices", []):
            if isinstance(item, dict) and item.get("kind") == "free_window" and not item.get("start") and not item.get("end"):
                start, day = value.get("start_date"), item.get("day_date")
                try:
                    start = date.fromisoformat(start) if isinstance(start, str) else start
                    day = date.fromisoformat(day) if isinstance(day, str) else day
                    if whole_day_quote(item.get("source_quote", ""), day, start):
                        item = {**item, "kind":"blank_day", "label":item["source_quote"]}
                except (ValueError, TypeError):
                    pass
            result["choices"].append(item)
        return result


def normalize_creation_evidence(decision, message):
    """Repair source representation only, never invent intent or identities.

    Creation owns the entire new-trip request, including earlier literal place
    selections. A unique current affirmative creation clause can supply its
    exact authorization quote; later policy still checks negation/revocation.
    """
    if decision.intent != "create" or decision.creation is None:
        return decision
    quote=decision.authorization_quote
    if not quote or quote not in message:
        clauses=[part.strip() for part in re.split(r"[，,。；;!?！？\n]",message) if part.strip()]
        candidates=[part for part in clauses if re.match(r"(?:请|帮我|替我|麻烦|能不能帮我|能否帮我)?(?:创建|生成|制定|规划)",part)]
        if len(candidates)==1:
            quote=candidates[0]
    mapping={};choices=[]
    for choice in decision.creation.choices:
        label=choice.label
        if choice.origin=="user_explicit" and choice.source_quote and choice.source_quote in message:
            subject=re.fullmatch(r"(.{2,80}?)选[^，,。；;]+",choice.source_quote.strip())
            base=re.split(r"[（(]",label,maxsplit=1)[0].strip()
            if subject and base.startswith(subject[1]) and len(subject[1])>=2:
                mapping[base]=subject[1];label=subject[1]
        choices.append(choice.model_copy(update={"label":label}))
    draft=decision.planning_draft
    if draft is not None:
        operations=[op.model_copy(update={"raw_text":message,
            "place_mentions":[mapping.get(name,name) for name in op.place_mentions]})
            if op.operation=="create_plan" else op for op in draft.operations]
        draft=draft.model_copy(update={"operations":operations})
    creation=decision.creation.model_copy(update={"choices":choices})
    # Explicit departure and finish bounds require a timed candidate. These
    # are constraints for the existing Planner, not ready-made saved choices.
    depart=re.search(r"\d{1,2}(?:点|时|:\d{2})[^，,。；;]{0,8}出发",message)
    finish=re.search(r"\d{1,2}(?:点|时|:\d{2})[^，,。；;]{0,8}(?:结束|返回)",message)
    if depart and finish:
        from app.assistant_capabilities import _non_authorizing_context
        if not _non_authorizing_context(message,depart[0]) and not _non_authorizing_context(message,finish[0]):
            creation=creation.model_copy(update={"flexible":False,"choices":[]})
    return decision.model_copy(update={"authorization_quote":quote,"creation":creation,
        "names":[mapping.get(name,name) for name in decision.names],"planning_draft":draft})


def approved_draft(decision, message):
    draft = decision.planning_draft
    if draft is None:
        return None
    if any(op.raw_text not in message or any(name not in op.raw_text
           for name in [*op.place_mentions, *op.activity_mentions]) for op in draft.operations):
        raise ValueError("操作及地点必须绑定本次用户原句")
    if decision.intent not in {"create", "modify"}:
        raise ValueError("读取决策不能授予规划操作")
    from app.assistant_capabilities import affirmative_action_source, affirmative_entity_source
    verbs = {"add_activity":r"加入|添加|增加|纳入|放进", "remove_activity":r"撤掉|撤销|取消|删除|删掉|不去",
        "replace_activity":r"换成|换掉|替换", "reorder_activities":r"移到|挪|晚|提前|延后|调整|顺序|改",
        "optimize_route":r"优化|协调|调整", "adjust_budget":r"控制|调整|预算", "weather_replan":r"调整|改|换",
        "create_plan":r"创建|生成|安排|规划", "replan_trip":r"重排|重做|重新|调整|安排|规划"}
    for op in draft.operations:
        if op.operation not in verbs:
            continue
        # Copy the containing clause from its beginning. A model cannot strip
        # a date/negator and borrow authority from another positive operation.
        if message.count(op.raw_text) != 1:
            raise ValueError("操作原句存在多个对应位置，请明确各项操作")
        prefix = re.split(r"[，,。；;!?！？\n]", message[:message.index(op.raw_text)])[-1].strip()
        if prefix and not re.fullmatch(r"(?:请|麻烦|帮我|替我|请你|给我|现在|实际)*", prefix):
            raise ValueError("操作必须保留完整原句限定条件")
        if (not affirmative_action_source(message, op.raw_text, verbs[op.operation]) or
                re.match(r"\s*(?:假设|假如|如果|先别|不要|不用)", op.raw_text)):
            raise ValueError("每个操作都需要本次肯定请求，否定或假设子句不授予操作权限")
        if op.operation not in {"create_plan", "replan_trip"} and any(
                not affirmative_entity_source(message, op.raw_text, verbs[op.operation], name)
                for name in [*op.place_mentions, *op.activity_mentions]):
            raise ValueError("每个操作目标都需绑定其自身的肯定请求，不能借用其他地点的授权")
    return draft.model_copy(update={"parser":"hybrid", "parser_version":"approved-operation-v2"}, deep=True)


def _quoted_dates(text, today):
    from app.assistant_memory import anchored_date
    values = []
    for token in re.finditer(r"20\d{2}-\d{1,2}-\d{1,2}|(?:20\d{2}年)?\d{1,2}月\d{1,2}[日号]?|今天|明天|后天", text):
        value = anchored_date(token[0], today)
        if value:
            values.append(date.fromisoformat(value))
    # Explicit same-month ranges may omit the second month/year.
    short = re.search(r"(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})[日号]?(?:到|至|[-—–～~])(\d{1,2})[日号]", text)
    if short:
        first = date.fromisoformat(anchored_date(f"{short[1] or today.year}年{short[2]}月{short[3]}日", today))
        values.extend([first, first.replace(day=int(short[4]))])
    return sorted(set(values))


def approved_tool_decision(decision, message, envelope, *, today):
    from app.assistant_service import ToolDecision
    from app.assistant_memory import memory_prompt
    if decision.intent == "modify":
        return ToolDecision(tool="plan_trip", reply="准备候选调整。", planning_request=message)
    proposal = decision.creation
    if proposal is None:
        return ToolDecision(tool="reply", reply="请提供这次旅行的城市和明确日期，我再准备可确认的候选。")
    effective = memory_prompt(envelope)
    slots = effective.get("slots", {})
    city = proposal.destination or (slots.get("city") or {}).get("value", "")
    if not city or (city.removesuffix("市") not in message and city.removesuffix("市") !=
                    str((slots.get("city") or {}).get("value", "")).removesuffix("市")):
        return ToolDecision(tool="reply", reply="想去哪个城市走走？")
    quoted = _quoted_dates(decision.authorization_quote, today)
    saved_start = (slots.get("start_date") or {}).get("value")
    start = date.fromisoformat(saved_start) if saved_start else (quoted[0] if quoted else None)
    if start is None or proposal.start_date is not None and proposal.start_date != start:
        return ToolDecision(tool="reply", reply="请明确这次的出发日期。")
    from app.travel_language import trip_duration
    from app.requirement_language import current_user_evidence_reason
    duration = ((slots.get("duration_days") or {}).get("value") or trip_duration(decision.authorization_quote)
        or (trip_duration(message) if current_user_evidence_reason(message, message) is None else None))
    end = quoted[-1] if len(quoted)>1 else start + timedelta(days=int(duration)-1) if duration else None
    if end is None or proposal.end_date is not None and proposal.end_date != end:
        return ToolDecision(tool="reply", reply="准备玩几天，还是已经有返程日期了？")
    budget = proposal.total_budget_fen
    if budget is not None:
        source = str((slots.get("budget") or {}).get("value", "")) + " " + decision.authorization_quote
        # A matching amount does not prove its unit. Only an explicit total
        # can populate the formal Trip total; other budgets remain verbatim.
        total_clauses = [re.fullmatch(
            r"\s*(?:这次|本次)?(?:旅行|行程|整趟)?(?:总预算|全部预算|花费总额)\s*"
            r"(?:为|是|约|最多|不超过|控制在)?\s*(\d+(?:\.\d+)?)\s*元[。.!！]?\s*", part)
            for part in re.split(r"[，,。；;\n]", source)]
        amounts = [round(float(m[1])*100) for m in total_clauses if m]
        if budget not in amounts:
            budget = None
    choices=[]
    for choice in proposal.choices if proposal.flexible else []:
        if choice.origin != "user_explicit" or choice.source_quote not in message or choice.kind != "blank_day" and choice.label not in choice.source_quote:
            return ToolDecision(tool="reply", reply="请确认各地点或留白对应的原始要求。")
        try:
            choices.append(CreationChoice.model_validate(choice.model_dump()))
        except ValueError:
            return ToolDecision(tool="reply",reply="这项局部留白或预约还缺少明确的日期、起止时间；可以先保留未定，不会猜测钟点。")
    preferences = "\n".join(dict.fromkeys([*[p["value"] for p in
        [*effective.get("preferences", []), *effective.get("requirements", [])]], message]))
    return ToolDecision(tool="create_trip", reply="准备创建预览。", destination=city,
        start_date=start, end_date=end, total_budget_fen=budget, flexible=proposal.flexible,
        choices=choices, preferences=preferences, planning_request=message)
