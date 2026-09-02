import re
import uuid
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Activity, DayPlan, PlaceCandidate, Trip
from app.repository import TripNotFoundError
from app.schemas import (
    PlanningIntent,
    PlanningIntentParseRequest,
    PlanningIntentResolution,
    PlanningIntentType,
    PlanningRequest,
    PlanningTimeScope,
    TripPace,
)


PARSER_VERSION = "rules-v1"
T = TypeVar("T")

_DAY_PATTERN = re.compile(r"第\s*([一二三四五六七八九十两\d]+)\s*天")
_ISO_DATE_PATTERN = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_MONTH_DAY_PATTERN = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
_PROTECT_PATTERNS = (
    re.compile(r"保留\s*([^，。；,;]+)"),
    re.compile(r"([^，。；,;]+?)\s*(?:不要动|别动|不要删除|别删除)"),
)
_PLACE_PATTERNS = (
    re.compile(r"(?:想去|加入|添加|增加)\s*([^，。；,;]+)"),
)

_OUT_OF_SCOPE_MARKERS = (
    "删除整个行程",
    "删除这次旅行",
    "删除旅行",
)

_FULL_REPLAN_MARKERS = (
    "重新规划",
    "重做整个",
    "重做全程",
    "全部重排",
    "整体重排",
    "推倒重来",
    "从头规划",
    "重新安排整个行程",
)
_PLAN_MARKERS = (
    "规划行程",
    "规划这次旅行",
    "帮我规划",
    "生成行程",
    "制定行程",
    "安排行程",
    "做个行程",
    "做一份行程",
)
_LOCAL_CHANGE_MARKERS = (
    "调整",
    "修改",
    "换掉",
    "替换",
    "移到",
    "移动",
    "删掉",
    "删除",
    "保留",
    "不要动",
    "别动",
    "太满",
    "太赶",
    "轻松一点",
    "放松一点",
    "想去",
    "加入",
    "添加",
    "增加",
    "重新安排",
)


class IntentContextError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class _ActivityEntity:
    id: uuid.UUID
    day_id: uuid.UUID
    day_date: date
    aliases: tuple[str, ...]


def classify_planning_intent(
    message: str,
    *,
    has_activities: bool,
    has_selected_day: bool = False,
    has_selected_activity: bool = False,
) -> PlanningIntentType:
    """High-precision deterministic router used before an eventual model fallback."""

    normalized = _normalize_text(message)
    if any(marker in normalized for marker in _OUT_OF_SCOPE_MARKERS):
        return "unknown"
    has_day_reference = bool(
        _DAY_PATTERN.search(message)
        or _ISO_DATE_PATTERN.search(message)
        or _MONTH_DAY_PATTERN.search(message)
        or "首日" in message
    )
    if has_day_reference or has_selected_day or has_selected_activity:
        if any(marker in normalized for marker in _PLAN_MARKERS + _LOCAL_CHANGE_MARKERS):
            return "modify_day"
    if any(marker in normalized for marker in _FULL_REPLAN_MARKERS):
        return "replan_trip" if has_activities else "create_plan"
    if any(marker in normalized for marker in _LOCAL_CHANGE_MARKERS):
        return "modify_day"
    if any(marker in normalized for marker in _PLAN_MARKERS):
        return "replan_trip" if has_activities else "create_plan"
    return "unknown"


async def resolve_planning_intent(
    session: AsyncSession,
    trip_id: uuid.UUID,
    payload: PlanningIntentParseRequest,
) -> PlanningIntentResolution:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise TripNotFoundError
    days = list(
        (
            await session.scalars(
                select(DayPlan).where(DayPlan.trip_id == trip_id).order_by(DayPlan.position)
            )
        ).all()
    )
    days_by_id = {day.id: day for day in days}
    days_by_date = {day.date: day for day in days}
    activity_rows = list(
        (
            await session.execute(
                select(Activity, DayPlan, PlaceCandidate)
                .join(DayPlan, Activity.day_plan_id == DayPlan.id)
                .join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id)
                .where(DayPlan.trip_id == trip_id)
            )
        ).tuples()
    )
    entities = [
        _ActivityEntity(
            id=activity.id,
            day_id=day.id,
            day_date=day.date,
            aliases=tuple(
                value
                for value in (activity.custom_name, place.name)
                if value
            ),
        )
        for activity, day, place in activity_rows
    ]
    entities_by_id = {entity.id: entity for entity in entities}

    if payload.selected_day_id is not None and payload.selected_day_id not in days_by_id:
        raise IntentContextError(
            "selected_day_not_in_trip", "selected day does not belong to this trip"
        )
    if (
        payload.selected_activity_id is not None
        and payload.selected_activity_id not in entities_by_id
    ):
        raise IntentContextError(
            "selected_activity_not_in_trip",
            "selected activity does not belong to this trip",
        )

    intent_type = classify_planning_intent(
        payload.message,
        has_activities=bool(entities),
        has_selected_day=payload.selected_day_id is not None,
        has_selected_activity=payload.selected_activity_id is not None,
    )
    ambiguities: list[str] = []
    missing_fields: list[str] = []
    target_day: DayPlan | None = None
    scope = _parse_time_scope(payload.message, trip, days, ambiguities)
    if scope is not None and scope.day_date is not None:
        target_day = days_by_date.get(scope.day_date)
    if target_day is None and payload.selected_day_id is not None:
        target_day = days_by_id[payload.selected_day_id]
        scope = _scope_for_day(target_day, days, scope)
    if target_day is None and payload.selected_activity_id is not None:
        target_day = days_by_id[entities_by_id[payload.selected_activity_id].day_id]
        scope = _scope_for_day(target_day, days, scope)

    protected_activity_ids = _resolve_protected_activities(
        payload.message,
        entities,
        payload.selected_activity_id,
        ambiguities,
    )
    if target_day is None and protected_activity_ids:
        protected_days = {
            entities_by_id[activity_id].day_id for activity_id in protected_activity_ids
        }
        if len(protected_days) == 1:
            target_day = days_by_id[protected_days.pop()]
            scope = _scope_for_day(target_day, days, scope)

    if intent_type in {"create_plan", "replan_trip"} and not trip.destination.strip():
        missing_fields.append("destination")
    if intent_type == "modify_day" and target_day is None:
        missing_fields.append("target_day")
    if intent_type == "unknown":
        ambiguities.append("unsupported_or_ambiguous_intent")

    intent = PlanningIntent(
        intent_type=intent_type,
        source_text=payload.message,
        time_scope=scope,
        protected_activity_ids=protected_activity_ids,
        requested_place_queries=_extract_place_queries(payload.message),
        requested_pace=_parse_requested_pace(payload.message),
        missing_fields=_deduplicate(missing_fields),
        ambiguities=_deduplicate(ambiguities),
    )
    request = PlanningRequest(
        trip_id=trip_id,
        user_request=payload.message,
        intent=intent,
        entry_point=payload.entry_point,
        selected_day_id=payload.selected_day_id,
        selected_activity_id=payload.selected_activity_id,
        target_day_id=target_day.id if target_day is not None else None,
    )
    questions = _clarification_questions(intent)
    return PlanningIntentResolution(
        request=request,
        requires_clarification=bool(intent.missing_fields or intent.ambiguities),
        clarification_questions=questions,
        parser_version=PARSER_VERSION,
    )


def _parse_time_scope(
    message: str,
    trip: Trip,
    days: list[DayPlan],
    ambiguities: list[str],
) -> PlanningTimeScope | None:
    period = None
    if any(value in message for value in ("上午", "早上", "清晨")):
        period = "morning"
    elif any(value in message for value in ("下午", "午后")):
        period = "afternoon"
    elif any(value in message for value in ("晚上", "傍晚", "夜间")):
        period = "evening"
    elif any(value in message for value in ("全天", "一整天")):
        period = "full_day"

    day_number = 1 if "首日" in message else None
    match = _DAY_PATTERN.search(message)
    if match is not None:
        day_number = _parse_chinese_number(match.group(1))
    day_date = None
    iso_match = _ISO_DATE_PATTERN.search(message)
    month_day_match = _MONTH_DAY_PATTERN.search(message)
    try:
        if iso_match is not None:
            day_date = date(*(int(value) for value in iso_match.groups()))
        elif month_day_match is not None:
            day_date = date(
                trip.start_date.year,
                int(month_day_match.group(1)),
                int(month_day_match.group(2)),
            )
    except ValueError:
        ambiguities.append("invalid_calendar_date")

    if day_number is not None:
        if 1 <= day_number <= len(days):
            numbered_date = days[day_number - 1].date
            if day_date is not None and day_date != numbered_date:
                ambiguities.append("conflicting_day_references")
            else:
                day_date = numbered_date
        else:
            ambiguities.append("day_outside_trip")
    if day_date is not None and day_date not in {day.date for day in days}:
        ambiguities.append("date_outside_trip")
    if day_number is None and day_date is not None and day_date in {day.date for day in days}:
        day_number = next(index for index, day in enumerate(days, 1) if day.date == day_date)
    if day_number is None and day_date is None and period is None:
        return None
    return PlanningTimeScope(day_number=day_number, day_date=day_date, period=period)


def _scope_for_day(
    day: DayPlan,
    days: list[DayPlan],
    existing: PlanningTimeScope | None,
) -> PlanningTimeScope:
    return PlanningTimeScope(
        day_number=next(index for index, item in enumerate(days, 1) if item.id == day.id),
        day_date=day.date,
        period=existing.period if existing is not None else None,
    )


def _resolve_protected_activities(
    message: str,
    entities: list[_ActivityEntity],
    selected_activity_id: uuid.UUID | None,
    ambiguities: list[str],
) -> list[uuid.UUID]:
    mentions: list[str] = []
    for pattern in _PROTECT_PATTERNS:
        mentions.extend(match.group(1).strip() for match in pattern.finditer(message))
    resolved: list[uuid.UUID] = []
    for mention in mentions:
        normalized_mention = _normalize_entity(mention)
        if normalized_mention in {"这个", "这个活动", "这个地方", "它", "该活动"}:
            if selected_activity_id is not None:
                resolved.append(selected_activity_id)
            else:
                ambiguities.append(f"ambiguous_activity_reference:{mention}")
            continue
        matches = [
            entity.id
            for entity in entities
            if any(
                _normalize_entity(alias) == normalized_mention
                or _normalize_entity(alias) in normalized_mention
                for alias in entity.aliases
            )
        ]
        if len(matches) == 1:
            resolved.append(matches[0])
        elif not matches:
            ambiguities.append(f"activity_not_found:{mention}")
        else:
            ambiguities.append(f"activity_not_unique:{mention}")
    return _deduplicate(resolved)


def _extract_place_queries(message: str) -> list[str]:
    values: list[str] = []
    for pattern in _PLACE_PATTERNS:
        values.extend(match.group(1).strip() for match in pattern.finditer(message))
    return _deduplicate([value for value in values if value])


def _parse_requested_pace(message: str) -> TripPace | None:
    if any(value in message for value in ("别太满", "不要太满", "别太赶", "不要太赶", "轻松一点", "放松一点")):
        return "relaxed"
    if any(value in message for value in ("紧凑", "多安排", "高强度")):
        return "intensive"
    if any(value in message for value in ("适中", "均衡", "正常节奏")):
        return "balanced"
    return None


def _clarification_questions(intent: PlanningIntent) -> list[str]:
    questions: list[str] = []
    if "destination" in intent.missing_fields:
        questions.append("这次旅行要去哪个城市？")
    if "target_day" in intent.missing_fields:
        questions.append("你想调整旅行中的哪一天？")
    for ambiguity in intent.ambiguities:
        if ambiguity == "unsupported_or_ambiguous_intent":
            questions.append("你希望创建完整行程、重新规划全程，还是调整某一天？")
        elif ambiguity in {"day_outside_trip", "date_outside_trip", "invalid_calendar_date"}:
            questions.append("你提到的日期不在当前旅行范围内，请重新指定日期。")
        elif ambiguity == "conflicting_day_references":
            questions.append("你提到的第几天和具体日期不一致，请确认目标日期。")
        elif ambiguity.startswith("activity_not_found:"):
            questions.append(f"当前行程中没有找到“{ambiguity.split(':', 1)[1]}”，请重新指定活动。")
        elif ambiguity.startswith("activity_not_unique:"):
            questions.append(f"当前行程中有多个“{ambiguity.split(':', 1)[1]}”，请选择具体活动。")
        elif ambiguity.startswith("ambiguous_activity_reference:"):
            questions.append("请明确指出需要保留的活动。")
    return _deduplicate(questions)


def _parse_chinese_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    normalized = value.replace("两", "二")
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if normalized == "十":
        return 10
    if "十" in normalized:
        left, right = normalized.split("十", 1)
        return (digits.get(left, 1) * 10) + digits.get(right, 0)
    return digits.get(normalized, 0)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def _normalize_entity(value: str) -> str:
    return re.sub(r"[\s，。！？、,.!?;；]", "", value.strip().lower())


def _deduplicate(values: list[T]) -> list[T]:
    return list(dict.fromkeys(values))
