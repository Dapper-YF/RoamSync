"""Translate the one source-bound semantic decision into existing operations.

No model, Session, generated IDs or write authority lives in this module.
"""
import re
from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.flexible_creation import CreationChoice
from app.schemas import SemanticIntentDraft


class CreationProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    destination: str = Field(default="", max_length=120)
    start_date: date | None = None
    end_date: date | None = None
    total_budget_fen: int | None = Field(default=None, gt=0, le=100_000_000)
    flexible: bool = False
    choices: list[CreationChoice] = Field(default_factory=list, max_length=30)

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


def approved_draft(decision, message):
    draft = decision.planning_draft
    if draft is None:
        return None
    if any(op.raw_text not in message or any(name not in op.raw_text
           for name in [*op.place_mentions, *op.activity_mentions]) for op in draft.operations):
        raise ValueError("操作及地点必须绑定本次用户原句")
    if decision.intent not in {"create", "modify"}:
        raise ValueError("读取决策不能授予规划操作")
    from app.assistant_capabilities import _non_authorizing_context
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
        matches = list(re.finditer(verbs[op.operation], op.raw_text))
        if (_non_authorizing_context(message, op.raw_text) or
                matches and all(_non_authorizing_context(op.raw_text, match[0]) for match in matches) or
                re.match(r"\s*(?:假设|假如|如果|先别|不要|不用)", op.raw_text)):
            raise ValueError("每个操作都需要本次肯定请求，否定或假设子句不授予操作权限")
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
    duration = (slots.get("duration_days") or {}).get("value") or trip_duration(decision.authorization_quote)
    end = quoted[-1] if len(quoted)>1 else start + timedelta(days=int(duration)-1) if duration else None
    if end is None or proposal.end_date is not None and proposal.end_date != end:
        return ToolDecision(tool="reply", reply="准备玩几天，还是已经有返程日期了？")
    budget = proposal.total_budget_fen
    if budget is not None:
        source = str((slots.get("budget") or {}).get("value", "")) + " " + decision.authorization_quote
        # A matching amount does not prove its unit. Only an explicit total
        # can populate the formal Trip total; other budgets remain verbatim.
        total_clauses = [part for part in re.split(r"[，,。；;\n]", source)
            if re.search(r"(?:旅行|行程|整趟|这次)?(?:总预算|全部预算|花费总额)", part)
            and not re.search(r"不是|取消|撤销|待定|不限", part)]
        amounts = [round(float(m[1])*100) for part in total_clauses for m in re.finditer(
            r"(?:总预算|全部预算|花费总额)\s*(?:为|是|约|最多|不超过|控制在)?\s*(\d+(?:\.\d+)?)\s*元", part)]
        if budget not in amounts:
            budget = None
    for choice in proposal.choices:
        if choice.origin != "user_explicit" or choice.source_quote not in message or choice.kind != "blank_day" and choice.label not in choice.source_quote:
            return ToolDecision(tool="reply", reply="请确认各地点或留白对应的原始要求。")
    preferences = "\n".join(dict.fromkeys([*[p["value"] for p in
        [*effective.get("preferences", []), *effective.get("requirements", [])]], message]))
    return ToolDecision(tool="create_trip", reply="准备创建预览。", destination=city,
        start_date=start, end_date=end, total_budget_fen=budget, flexible=proposal.flexible,
        choices=proposal.choices, preferences=preferences, planning_request=message)
