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
    duration = (slots.get("duration_days") or {}).get("value")
    end = start + timedelta(days=int(duration)-1) if duration else quoted[-1] if len(quoted)>1 else None
    if end is None or proposal.end_date is not None and proposal.end_date != end:
        return ToolDecision(tool="reply", reply="准备玩几天，还是已经有返程日期了？")
    budget = proposal.total_budget_fen
    if budget is not None:
        source = str((slots.get("budget") or {}).get("value", "")) + " " + decision.authorization_quote
        amounts = [round(float(m[0])*100) for m in re.finditer(r"\d+(?:\.\d+)?(?=\s*元)", source)]
        if budget not in amounts:
            return ToolDecision(tool="reply", reply="请确认旅行总预算的金额与口径。")
    for choice in proposal.choices:
        if choice.origin != "user_explicit" or choice.source_quote not in message or choice.kind != "blank_day" and choice.label not in choice.source_quote:
            return ToolDecision(tool="reply", reply="请确认各地点或留白对应的原始要求。")
    preferences = "\n".join(dict.fromkeys([*[p["value"] for p in
        [*effective.get("preferences", []), *effective.get("requirements", [])]], message]))
    return ToolDecision(tool="create_trip", reply="准备创建预览。", destination=city,
        start_date=start, end_date=end, total_budget_fen=budget, flexible=proposal.flexible,
        choices=proposal.choices, preferences=preferences, planning_request=message)
