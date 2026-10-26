import logging
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Protocol, TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Activity, DayPlan, PlaceCandidate, Trip, TripExecution
from app.repository import TripNotFoundError
from app.planning_errors import PlannerProviderError
from app.travel_language import is_generic_place_quantity
from app.schemas import (
    PlanningIntent,
    GroundedIntent,
    IntentConstraints,
    IntentOperationType,
    IntentPolicyDecision,
    PlanningIntentParseRequest,
    PlanningIntentResolution,
    PlanningIntentType,
    PlanningRequest,
    PlanningTimeScope,
    SemanticIntentDraft,
    SemanticIntentOperation,
    TripPace,
)


PARSER_VERSION = "rules-v1"
logger = logging.getLogger(__name__)
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

_REPLACE_PATTERN = re.compile(
    r"(?:把)?\s*([^，。；,;]+?)\s*(?:换成|替换成|改成)\s*([^，。；,;]+)"
)
_REMOVE_PATTERN = re.compile(
    r"(?:删掉|删除|取消|不去)\s*([^，。；,;]+)"
)
_MOVE_PATTERN = re.compile(
    r"(?:把)?\s*([^，。；,;]+?)\s*(?:移到|移动到|调到|改到|提前到|延后到|交换顺序)"
)
_RELATIVE_DATE_PATTERN = re.compile(r"今天|明天|后天|剩余行程")
_EXPLICIT_NON_PLANNING_MARKERS = (
    "订票", "预订酒店", "航班", "你好", "谢谢", "为什么", "解释", "预算是多少",
    "还剩多少预算", "天气怎么样", "删除整个行程", "删除这次旅行",
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
    "整趟旅行重新安排",
    "重新安排行程",
    "重新做一份",
    "整个安排重做",
    "完整行程",
    "所有天都重新排",
    "重做这次旅行",
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
    "改到",
    "节奏放慢",
    "松一点",
    "从容一点",
    "休息时间",
    "宽松些",
)


class IntentContextError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class UnsupportedPlanningIntentError(Exception):
    def __init__(self, route: str, message: str) -> None:
        self.route = route
        self.message = message
        super().__init__(message)


class SemanticIntentProvider(Protocol):
    async def extract(self, message: str, context: dict[str, Any]) -> SemanticIntentDraft: ...


@dataclass(frozen=True)
class _ActivityEntity:
    id: uuid.UUID
    day_id: uuid.UUID
    day_date: date
    aliases: tuple[str, ...]
    category: str = ""
    scheduled_time: time | None = None


def is_advice_request(message: str) -> bool:
    """Questions about an arrangement do not authorize producing a replacement."""
    # Imperative clauses can accompany a question: explain AND make this change.
    imperative = re.search(r"(?:请|帮我|替我|给我|直接)(?:把[^，。；？?]+)?(?:重新规划|重排|调整|修改|删除|添加|安排|生成)|[，。；;]\s*(?:把.+(?:改成|换成|移到)|重新规划|删掉|添加)", message)
    if imperative:
        return False
    if re.search(r"(?:能不能|能否|可以)(?:帮我)?把[^，。；？?]+(?:换成|改成|移到|删掉)", message):
        return False
    if re.search(r"怎么|怎样|如何|为什么|多少|哪里|哪些|是否|有没有|[吗呢][？?]?$", message):
        return True
    return any(word in message for word in (
        "为什么", "解释", "介绍", "怎么看", "怎么样", "怎样", "怎么走", "怎么去", "怎么逛", "怎么玩",
        "怎么安排", "怎么规划", "怎么调整", "什么建议", "建议我", "推荐", "值得", "合理吗", "会不会", "适合吗",
        "有哪些", "有什么", "是什么", "是多少", "多少钱", "多少预算", "花了多少", "还剩多少", "你好", "谢谢",
        "先不修改", "先别修改", "只问", "只解释", "只回答", "只分析", "游玩的理由", "安排的理由",
    ))


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
    if is_advice_request(message):
        return "unknown"
    has_day_reference = bool(
        _DAY_PATTERN.search(message)
        or _ISO_DATE_PATTERN.search(message)
        or _MONTH_DAY_PATTERN.search(message)
        or "首日" in message
    )
    if not has_day_reference and not _RELATIVE_DATE_PATTERN.search(message) and not re.search(r"当天|这一天|这天|当日|选中|这个活动", message):
        if re.search(r"每天|每日|每一天", message) and re.search(r"增加|添加|加[一二三两\d]|多安排|少安排|景点|景区", message):
            return "replan_trip" if has_activities else "create_plan"
        if not has_activities and any(marker in normalized for marker in _PLAN_MARKERS + _FULL_REPLAN_MARKERS + ("想去", "加入", "添加")):
            return "create_plan"
        if re.search(r"(?:行程|旅行)(?:中|里)?.{0,8}(?:包含|包括|看到|游览|游玩)|(?:想去|希望去).+[、，,和]", message):
            return "replan_trip" if has_activities else "create_plan"
    # A default UI selection is context, not an instruction to shorten a full trip.
    if not has_day_reference and any(word in normalized for word in ("这次旅行", "整个行程", "整趟旅行")) and any(word in normalized for word in ("丰富", "充实", "多样")):
        return "replan_trip" if has_activities else "create_plan"
    if not has_day_reference and any(marker in normalized for marker in _FULL_REPLAN_MARKERS):
        return "replan_trip" if has_activities else "create_plan"
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
    *,
    semantic_provider: SemanticIntentProvider | None = None,
    default_planning_intent: PlanningIntentType | None = None,
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
            category=place.category,
            scheduled_time=activity.scheduled_time,
            aliases=tuple(
                value
                for value in (activity.custom_name, place.name)
                if value
            ),
        )
        for activity, day, place in activity_rows
    ]
    entities_by_id = {entity.id: entity for entity in entities}
    candidate_rows = list(
        (
            await session.scalars(
                select(PlaceCandidate).where(PlaceCandidate.trip_id == trip_id)
            )
        ).all()
    )

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

    scope_message, names_full_range = _without_trip_date_range(payload.message, trip)
    intent_type = classify_planning_intent(
        scope_message,
        has_activities=bool(entities),
        has_selected_day=payload.selected_day_id is not None,
        has_selected_activity=payload.selected_activity_id is not None,
    )
    # run_type is UI context, never authorization to turn arbitrary text into a plan.
    ambiguities: list[str] = []
    missing_fields: list[str] = []
    target_day: DayPlan | None = None
    execution = await session.scalar(
        select(TripExecution).where(
            TripExecution.trip_id == trip_id,
            TripExecution.status.in_(("in_progress", "paused")),
        )
    )
    local_today = datetime.now(ZoneInfo(trip.timezone)).date()
    relative_date_base = (
        execution.current_date
        if execution is not None
        else local_today if trip.start_date <= local_today <= trip.end_date else None
    )
    scope = _parse_time_scope(
        scope_message, trip, days, ambiguities, relative_date_base=relative_date_base
    )
    if names_full_range and scope is None and intent_type != "unknown":
        intent_type = "replan_trip" if entities else "create_plan"
    if scope is not None and scope.day_date is not None:
        target_day = days_by_date.get(scope.day_date)
    if target_day is None and intent_type not in {"create_plan", "replan_trip"} and payload.selected_day_id is not None:
        target_day = days_by_id[payload.selected_day_id]
        scope = _scope_for_day(target_day, days, scope)
    if target_day is None and intent_type not in {"create_plan", "replan_trip"} and payload.selected_activity_id is not None:
        target_day = days_by_id[entities_by_id[payload.selected_activity_id].day_id]
        scope = _scope_for_day(target_day, days, scope)

    protected_activity_ids = _resolve_protected_activities(
        payload.message,
        entities,
        payload.selected_activity_id,
        ambiguities,
        target_day_id=target_day.id if target_day else None,
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
    semantic_draft = _build_rule_semantic_draft(payload.message, intent_type, scope, scope_message=scope_message)
    if (
        semantic_provider is not None
        and semantic_draft.primary_intent == "unsupported"
        and semantic_draft.confidence < 0.9
    ):
        semantic_context = {
                "entry_point": payload.entry_point,
                "selected_day_id": (
                    str(payload.selected_day_id) if payload.selected_day_id else None
                ),
                "selected_activity_id": (
                    str(payload.selected_activity_id)
                    if payload.selected_activity_id
                    else None
                ),
                "trip": {
                    "destination": trip.destination,
                    "start_date": trip.start_date.isoformat(),
                    "end_date": trip.end_date.isoformat(),
                    "timezone": trip.timezone,
                },
                "days": [
                    {
                        "day_id": str(day.id),
                        "date": day.date.isoformat(),
                        "position": day.position,
                    }
                    for day in days
                ],
                "activities": [
                    {
                        "activity_id": str(entity.id),
                        "day_id": str(entity.day_id),
                        "date": entity.day_date.isoformat(),
                        "aliases": list(entity.aliases),
                    }
                    for entity in entities
                ],
        }
        for attempt in range(2):
            try:
                semantic_draft = await semantic_provider.extract(
                    payload.message, semantic_context
                )
                break
            except PlannerProviderError as exc:
                may_retry_output = exc.code in {
                    "intent_invalid_output",
                    "intent_incomplete_output",
                }
                if attempt == 0 and (exc.retryable or may_retry_output):
                    continue
                logger.warning("semantic intent fallback failed: %s", exc.code)
    grounded_intent = _ground_semantic_intent(
        semantic_draft,
        trip_id=trip_id,
        target_day=target_day,
        selected_activity_id=payload.selected_activity_id,
        protected_activity_ids=protected_activity_ids,
        entities=entities,
        candidates=candidate_rows,
        inherited_missing_fields=intent.missing_fields,
        inherited_ambiguities=intent.ambiguities,
    )
    grounded_intent = _reconcile_grounded_ambiguities(grounded_intent)
    policy_decision = _decide_intent_policy(grounded_intent)
    if policy_decision.route == "clarify":
        questions.extend(_grounding_questions(grounded_intent))
    questions = _deduplicate(questions)
    if policy_decision.route == "clarify" and not questions:
        raise ValueError("clarification policy requires at least one question")
    return PlanningIntentResolution(
        request=request,
        requires_clarification=policy_decision.route == "clarify",
        clarification_questions=questions,
        parser_version=PARSER_VERSION,
        semantic_draft=semantic_draft,
        grounded_intent=grounded_intent,
        policy_decision=policy_decision,
    )


def _without_trip_date_range(message: str, trip: Trip) -> tuple[str, bool]:
    """A connected full-trip range is context; keep any separate local target."""
    patterns = (
        re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})\s*(?:至|到|~|～|—|–|-)\s*(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)"),
        re.compile(r"(?<!\d)(\d{1,2})月(\d{1,2})[日号]\s*(?:至|到|~|～|—|–|-)\s*(\d{1,2})月(\d{1,2})[日号]"),
    )
    found = False
    for pattern in patterns:
        def replace(match):
            nonlocal found
            values = tuple(map(int, match.groups()))
            try:
                if len(values) == 6:
                    start, end = date(*values[:3]), date(*values[3:])
                else:
                    start = date(trip.start_date.year, *values[:2])
                    end = date(trip.end_date.year, *values[2:])
            except ValueError:
                return match.group(0)
            if start == trip.start_date and end == trip.end_date and start != end:
                found = True
                return ""
            return match.group(0)
        message = pattern.sub(replace, message)
    return message, found


def _change_scope_text(message: str) -> str:
    """Dates in unchanged clauses describe boundaries, not the mutation target."""
    parts = re.split(r"[，,。；;]", message)
    kept = []
    for part in parts:
        boundary = re.search(r"不变|照旧|不调整|不要改动", part)
        remaining = re.sub(r"不调整|不要改动", "", part)
        if boundary and not re.search(r"调整|修改|加入|添加|增加|移到|替换|删除", remaining):
            continue
        kept.append(part)
    return "，".join(kept)


def _parse_time_scope(
    message: str,
    trip: Trip,
    days: list[DayPlan],
    ambiguities: list[str],
    *,
    relative_date_base: date | None,
) -> PlanningTimeScope | None:
    message = _change_scope_text(message)
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

    relative_match = _RELATIVE_DATE_PATTERN.search(message)
    if relative_match is not None and relative_match.group(0) != "剩余行程":
        if relative_date_base is None:
            ambiguities.append("relative_date_reference_missing")
        else:
            offset = {"今天": 0, "明天": 1, "后天": 2}[relative_match.group(0)]
            relative_date = relative_date_base + timedelta(days=offset)
            if day_date is not None and day_date != relative_date:
                ambiguities.append("conflicting_day_references")
            else:
                day_date = relative_date

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


def _trip_setting_kind(mention: str) -> str | None:
    """Recognize complete setting references, never substrings of place names."""
    value = _normalize_entity(mention)
    value = re.sub(r"^(?:(?:请|把|将|保留|保持|维持|沿用|原有|原来|现有|当前|已保存)(?:的)?)+", "", value)
    value = re.sub(r"(?:保持|维持)?(?:不变|照旧|不调整|不要改动|不要动|别动)$", "", value)
    if re.fullmatch(r"(?:总|每日|每天|旅行|行程)?预算(?:上限)?", value):
        return "budget"
    if re.fullmatch(r"(?:出发|返程|旅行|行程|开始|结束)?日期|目的地|目的城市|出行人数|旅行人数|旅行天数|出行天数|交通方式|出行方式|旅行偏好|住宿地点", value):
        return "trip_setting"
    return None


def _resolve_protected_activities(
    message: str,
    entities: list[_ActivityEntity],
    selected_activity_id: uuid.UUID | None,
    ambiguities: list[str],
    *,
    target_day_id: uuid.UUID | None = None,
) -> list[uuid.UUID]:
    mentions: list[str] = []
    for pattern in _PROTECT_PATTERNS:
        for match in pattern.finditer(message):
            # Soft preservation language is a planning goal, not a hard
            # prohibition on changing the named activities. Assistant may
            # expand "尽量保留现有活动" into a list of formal activity names;
            # treating that list as protected makes those activities
            # unavailable to Planner while destination research marks them as
            # mandatory, producing an impossible candidate contract.
            if re.search(r"(?:尽量|尽可能|优先|最好能)\s*$", message[:match.start()]):
                continue
            captured = match.group(1)
            # Assistant may phrase a soft preference as "保留现有活动尽量不要大改".
            # The protect regex captures the whole clause; this is not a named
            # activity reference and must not trigger clarification.
            if re.fullmatch(r"(?:原有|原来的|现有|当前|已有)?(?:的)?活动(?:尽量|尽可能|最好)?(?:不要|不必|无需)?(?:大改|改动|调整|变化)?", _normalize_entity(captured)):
                continue
            mentions.extend(_split_coordinated_mentions(captured))
    resolved: list[uuid.UUID] = []
    for mention in mentions:
        if _trip_setting_kind(mention):
            continue
        normalized_mention = _normalize_entity(mention)
        meal_group = re.fullmatch(r"(?:原有的?|原来的?|现有的?|所有的?|全部的?)?(?:[一二三四五六七八九十两\d]+(?:个|处|顿|家)?)?(餐厅|用餐点|用餐安排|正餐|早餐|午餐|晚餐)", normalized_mention)
        if meal_group:
            # Group references are grounded in actual activities and the requested day.
            meal = meal_group.group(1)
            scoped = [e for e in entities if e.category == "food" and (target_day_id is None or e.day_id == target_day_id)]
            if meal in {"早餐", "午餐", "晚餐"}:
                lower, upper = {"早餐": (0, 11), "午餐": (11, 16), "晚餐": (16, 24)}[meal]
                scoped = [e for e in scoped if e.scheduled_time and lower <= e.scheduled_time.hour < upper]
            if scoped:
                resolved.extend(e.id for e in scoped)
            else:
                ambiguities.append(f"activity_not_found:{mention}")
            continue
        # Qualities of a plan are not names of activities. Keep them in the
        # planner's request instead of inventing an unresolved entity.
        if re.fullmatch(r"(?:相邻|邻近|附近|顺路)(?:的)?(?:地点|景点|活动)|(?:足够|充足|合理|适当)?(?:的)?(?:休息|交通|机动|自由活动)时间", normalized_mention):
            continue
        if normalized_mention in {"这个", "这个活动", "这个地方", "它", "该活动"}:
            if selected_activity_id is not None:
                resolved.append(selected_activity_id)
            else:
                ambiguities.append(f"ambiguous_activity_reference:{mention}")
            continue
        # Natural references may prefix a restaurant name with "原有的午餐".
        # Match the grounded name as well as the original phrase, without guessing IDs.
        named_mention = re.sub(r"^(?:(?:原有|原来|现有|早餐|午餐|晚餐)(?:的)?)+", "", normalized_mention) or normalized_mention
        matches = [
            entity.id
            for entity in entities
            if any(
                _normalize_entity(alias) == normalized_mention
                or _normalize_entity(alias) in normalized_mention
                or normalized_mention in _normalize_entity(alias)
                or named_mention in _normalize_entity(alias)
                for alias in entity.aliases
            )
        ]
        if len(matches) == 1:
            resolved.append(matches[0])
        elif not matches:
            if not _is_plan_meta_activity_reference(normalized_mention):
                ambiguities.append(f"activity_not_found:{mention}")
        else:
            ambiguities.append(f"activity_not_unique:{mention}")
    return _deduplicate(resolved)


def _is_plan_meta_activity_reference(value: str) -> bool:
    """Ignore ungrounded plan properties captured as if they were activity names."""
    if value in {"顺序", "时长", "时间", "交通", "交通衔接", "安排", "内容", "要求", "上述要求"}:
        return True
    if re.fullmatch(
        r"主体(?:框架)?(?:的)?(?:基础上|前提下)(?:仅|优先)?(?:做)?(?:必要|小幅)?(?:微调|调整|优化|改动|变化)(?:顺序|时长|时间|交通衔接|交通|内容)?",
        value,
    ):
        return True
    return bool(re.fullmatch(
        r"(?:(?:原有|原来|现有|当前|已有|原)(?:的)?(?:活动|行程|安排)(?:的)?|主体(?:的)?)(?:基础上|前提下)?(?:小幅)?(?:微调|调整|优化|改动|变化)?(?:顺序|时长|时间|交通衔接|交通|内容)?(?:与|和|及)?(?:顺序|时长|时间|交通衔接|交通|内容)?",
        value,
    ))


def _extract_place_queries(message: str) -> list[str]:
    values: list[str] = []
    for pattern in _PLACE_PATTERNS:
        for match in pattern.finditer(message):
            values.extend(_split_coordinated_mentions(match.group(1)))
    return _deduplicate([value for value in values if value and not is_generic_place_quantity(value)])


def _split_coordinated_mentions(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[、和与及]", value) if item.strip()]


def _parse_requested_pace(message: str) -> TripPace | None:
    if any(value in message for value in ("别太满", "不要太满", "别太赶", "不要太赶", "轻松一点", "放松一点", "更轻松", "节奏放慢", "从容一点", "宽松些")):
        return "relaxed"
    if any(value in message for value in ("紧凑", "多安排", "高强度")):
        return "intensive"
    if any(value in message for value in ("适中", "均衡", "正常节奏")):
        return "balanced"
    return None


def _build_rule_semantic_draft(
    message: str,
    legacy_intent: PlanningIntentType,
    scope: PlanningTimeScope | None,
    *,
    scope_message: str | None = None,
) -> SemanticIntentDraft:
    normalized = _normalize_text(message)
    if any(marker in normalized for marker in _OUT_OF_SCOPE_MARKERS):
        return SemanticIntentDraft(
            primary_intent="unsupported",
            operations=[
                SemanticIntentOperation(operation="unsupported", raw_text=message)
            ],
            confidence=0.99,
            parser="rules",
            parser_version="rules-envelope-v1",
        )
    if is_advice_request(message):
        operation = "general_chat" if any(word in message for word in ("你好", "谢谢")) else "query_trip"
        return SemanticIntentDraft(
            primary_intent=operation,
            operations=[SemanticIntentOperation(operation=operation, raw_text=message)],
            confidence=0.98, parser="rules", parser_version="rules-answer-v2",
        )
    budget_query = any(
        value in message for value in ("预算是多少", "预算还有多少", "还剩多少预算", "花了多少", "费用是多少")
    )
    constraints = IntentConstraints(
        budget_must_not_increase=any(
            value in normalized
            for value in ("预算不要增加", "预算不增加", "不要增加预算", "别增加预算", "不能加钱")
        ),
        preferred_environment=(
            "indoor"
            if any(value in message for value in ("室内", "室内景点", "室内活动"))
            else "outdoor" if "室外" in message or "户外" in message else None
        ),
        requested_pace=_parse_requested_pace(message),
        weather_sensitive=any(value in message for value in ("天气", "下雨", "降雨", "高温", "暴雨")),
    )
    date_expression = _extract_date_expression(scope_message if scope_message is not None else message)
    operations: list[SemanticIntentOperation] = []

    def add_operation(
        operation: IntentOperationType,
        *,
        activity_mentions: list[str] | None = None,
        place_mentions: list[str] | None = None,
    ) -> None:
        if operation in {item.operation for item in operations}:
            return
        operations.append(
            SemanticIntentOperation(
                operation=operation,
                raw_text=message,
                date_expression=date_expression,
                period=scope.period if scope is not None else None,
                activity_mentions=activity_mentions or [],
                place_mentions=place_mentions or [],
                constraints=constraints,
            )
        )

    if legacy_intent == "create_plan":
        add_operation("create_plan")
    elif legacy_intent == "replan_trip":
        add_operation("replan_trip")

    replace_matches = list(_REPLACE_PATTERN.finditer(message))
    if replace_matches:
        add_operation(
            "replace_activity",
            activity_mentions=[match.group(1).strip() for match in replace_matches],
            place_mentions=[match.group(2).strip() for match in replace_matches],
        )
    remove_mentions = [match.group(1).strip() for match in _REMOVE_PATTERN.finditer(message)]
    if remove_mentions:
        add_operation("remove_activity", activity_mentions=remove_mentions)
    place_mentions = _extract_place_queries(message)
    if place_mentions and not replace_matches:
        add_operation("add_activity", place_mentions=place_mentions)
    # Keeping a saved budget limit does not request a financial change or cap
    # a new plan at the cost of its currently empty activity list.
    budget_action_text = "，".join(
        part for clause in re.split(r"[，。；,;]", message)
        for part in _split_coordinated_mentions(clause)
        if _trip_setting_kind(part) != "budget"
    )
    if not budget_query and any(
        value in budget_action_text for value in ("预算", "花费", "费用", "省钱", "加钱")
    ):
        add_operation("adjust_budget")
    if constraints.weather_sensitive:
        if legacy_intent != "unknown" or any(
            value in message for value in ("调整", "改", "换", "重排", "重新安排")
        ):
            add_operation("weather_replan")
        elif any(value in message for value in ("怎么样", "如何", "会不会", "多少度")):
            add_operation("query_trip")
    if any(value in message for value in ("路线", "顺路", "少走", "绕路", "交通")):
        add_operation("optimize_route")
    move_mentions = [match.group(1).strip() for match in _MOVE_PATTERN.finditer(message)]
    if move_mentions or any(value in message for value in ("移动", "提前", "延后", "交换顺序")):
        add_operation("reorder_activities", activity_mentions=move_mentions)

    if not operations:
        if legacy_intent == "modify_day":
            add_operation("replan_trip")
        elif budget_query or any(value in message for value in ("还剩多少", "为什么", "解释一下")):
            add_operation("query_trip")
        elif any(value in message for value in ("推荐", "有什么好吃", "有什么好玩", "去哪")):
            add_operation("search_places")
        elif any(value in message for value in ("订票", "预订", "订酒店", "航班")):
            add_operation("booking_assistance")
        elif any(value in message for value in ("你好", "谢谢", "嗨")):
            add_operation("general_chat")
        else:
            add_operation("unsupported")

    primary_operation = operations[0].operation
    primary_map = {
        "create_plan": "create_plan",
        "replan_trip": "replan_trip",
        "query_trip": "query_trip",
        "search_places": "search_places",
        "add_activity": "add_activity",
        "remove_activity": "remove_activity",
        "replace_activity": "replace_activity",
        "reorder_activities": "reorder_activities",
        "optimize_route": "optimize_route",
        "adjust_budget": "adjust_budget",
        "weather_replan": "weather_replan",
        "booking_assistance": "booking_assistance",
        "general_chat": "general_chat",
        "unsupported": "unsupported",
    }
    return SemanticIntentDraft(
        primary_intent=primary_map[primary_operation],
        operations=operations,
        confidence=0.98 if legacy_intent != "unknown" else 0.55,
        parser="rules",
        parser_version="rules-envelope-v1",
    )


def _extract_date_expression(message: str) -> str | None:
    message = _change_scope_text(message)
    for pattern in (_ISO_DATE_PATTERN, _MONTH_DAY_PATTERN, _DAY_PATTERN, _RELATIVE_DATE_PATTERN):
        match = pattern.search(message)
        if match is not None:
            return match.group(0)
    if "首日" in message:
        return "首日"
    return None


def _ground_semantic_intent(
    draft: SemanticIntentDraft,
    *,
    trip_id: uuid.UUID,
    target_day: DayPlan | None,
    selected_activity_id: uuid.UUID | None,
    protected_activity_ids: list[uuid.UUID],
    entities: list[_ActivityEntity],
    candidates: list[PlaceCandidate],
    inherited_missing_fields: list[str],
    inherited_ambiguities: list[str],
) -> GroundedIntent:
    target_activity_ids = list(protected_activity_ids)
    unresolved_activities: list[str] = []
    candidate_place_ids: list[uuid.UUID] = []
    unresolved_places: list[str] = []
    entity_by_id = {entity.id: entity for entity in entities}

    activity_mentions = _deduplicate(
        [mention for operation in draft.operations for mention in operation.activity_mentions]
    )
    for mention in activity_mentions:
        if is_generic_place_quantity(mention) or _trip_setting_kind(mention):
            continue
        normalized = _normalize_entity(mention)
        if normalized in {"这个", "这个活动", "这个地方", "它", "该活动", "那个景点"}:
            if selected_activity_id is not None:
                target_activity_ids.append(selected_activity_id)
            else:
                unresolved_activities.append(mention)
            continue
        matches = [
            entity.id
            for entity in entities
            if any(
                normalized == _normalize_entity(alias)
                or normalized in _normalize_entity(alias)
                or _normalize_entity(alias) in normalized
                for alias in entity.aliases
            )
        ]
        if len(matches) == 1:
            target_activity_ids.append(matches[0])
        else:
            unresolved_activities.append(mention)

    place_mentions = _deduplicate(
        [mention for operation in draft.operations for mention in operation.place_mentions]
    )
    for mention in place_mentions:
        if is_generic_place_quantity(mention):
            continue
        normalized = _normalize_entity(mention)
        # Existing formal activity identity wins over destination research.
        existing_matches = [entity.id for entity in entities
                            if (target_day is None or entity.day_id == target_day.id)
                            and (mention == str(entity.id) or any(normalized == _normalize_entity(alias) for alias in entity.aliases))]
        if len(existing_matches) == 1:
            target_activity_ids.append(existing_matches[0])
            continue
        if len(existing_matches) > 1:
            inherited_ambiguities.append(f"activity_not_unique:{mention}")
            continue
        matches = [
            candidate.id
            for candidate in candidates
            if normalized == _normalize_entity(candidate.name)
            or normalized in _normalize_entity(candidate.name)
            or _normalize_entity(candidate.name) in normalized
        ]
        if len(matches) == 1:
            candidate_place_ids.append(matches[0])
        elif not matches:
            unresolved_places.append(mention)
        else:
            inherited_ambiguities.append(f"place_not_unique:{mention}")

    constraints = IntentConstraints()
    for operation in draft.operations:
        value = operation.constraints
        constraints = IntentConstraints(
            budget_must_not_increase=(
                constraints.budget_must_not_increase or value.budget_must_not_increase
            ),
            max_additional_cost_fen=(
                value.max_additional_cost_fen
                if value.max_additional_cost_fen is not None
                else constraints.max_additional_cost_fen
            ),
            preferred_environment=value.preferred_environment or constraints.preferred_environment,
            max_walking_minutes=value.max_walking_minutes or constraints.max_walking_minutes,
            requested_pace=value.requested_pace or constraints.requested_pace,
            weather_sensitive=constraints.weather_sensitive or value.weather_sensitive,
            preserve_completed=True,
        )

    target_days = [target_day.id] if target_day is not None else []
    for activity_id in target_activity_ids:
        entity = entity_by_id.get(activity_id)
        if entity is not None:
            target_days.append(entity.day_id)
    grounded_missing_fields = list(inherited_missing_fields)
    operation_types = {operation.operation for operation in draft.operations}
    if (
        operation_types
        & {
            "add_activity",
            "remove_activity",
            "replace_activity",
            "reorder_activities",
            "optimize_route",
            "adjust_budget",
            "weather_replan",
        }
        and not target_days
        and not operation_types & {"create_plan", "replan_trip"}
    ):
        grounded_missing_fields.append("target_day")
    if (
        operation_types & {"remove_activity", "replace_activity", "reorder_activities"}
        and not target_activity_ids
        and not unresolved_activities
    ):
        grounded_missing_fields.append("target_activity")
    if (
        "add_activity" in operation_types
        and not candidate_place_ids
        and not target_activity_ids
        and not unresolved_places
        and not any(is_generic_place_quantity(mention) for mention in place_mentions)
    ):
        grounded_missing_fields.append("place_to_add")
    if (
        "replace_activity" in operation_types
        and not candidate_place_ids
        and not unresolved_places
    ):
        grounded_missing_fields.append("replacement_place")
    inherited_ambiguities = [
        item
        for item in inherited_ambiguities
        if not (
            item == "unsupported_or_ambiguous_intent"
            and draft.primary_intent != "unsupported"
        )
    ]
    return GroundedIntent(
        trip_id=trip_id,
        primary_intent=draft.primary_intent,
        operation_types=[operation.operation for operation in draft.operations],
        target_day_ids=_deduplicate(target_days),
        target_activity_ids=_deduplicate(target_activity_ids),
        candidate_place_ids=_deduplicate(candidate_place_ids),
        unresolved_activity_mentions=_deduplicate(unresolved_activities),
        unresolved_place_mentions=_deduplicate(unresolved_places),
        constraints=constraints,
        missing_fields=_deduplicate(grounded_missing_fields),
        ambiguities=list(inherited_ambiguities),
    )


def _decide_intent_policy(intent: GroundedIntent) -> IntentPolicyDecision:
    mutation_operations = {
        "create_plan",
        "replan_trip",
        "add_activity",
        "remove_activity",
        "replace_activity",
        "reorder_activities",
        "optimize_route",
        "adjust_budget",
        "weather_replan",
    }
    destructive_operations = {"remove_activity", "replace_activity", "adjust_budget"}
    operations = set(intent.operation_types)
    if operations & {"unsupported", "booking_assistance"}:
        return IntentPolicyDecision(
            operation_mode="reject",
            risk_level="prohibited",
            requires_confirmation=False,
            reasons=["operation_not_supported_in_agent_v1"],
            route="reject",
        )
    unresolved_mutation = bool(
        intent.unresolved_activity_mentions
        and operations & {"remove_activity", "replace_activity", "reorder_activities"}
    ) or bool(
        intent.unresolved_place_mentions
        and operations & {"add_activity", "replace_activity"}
    )
    if intent.missing_fields or intent.ambiguities or unresolved_mutation:
        return IntentPolicyDecision(
            operation_mode="clarify",
            risk_level="medium",
            requires_confirmation=False,
            reasons=["intent_or_entity_incomplete"],
            route="clarify",
        )
    if not operations & mutation_operations:
        return IntentPolicyDecision(
            operation_mode="answer_only",
            risk_level="low",
            requires_confirmation=False,
            reasons=["read_only_request"],
            route="answer",
        )
    high_risk = bool(operations & destructive_operations)
    return IntentPolicyDecision(
        operation_mode="preview_change",
        risk_level="high" if high_risk else "medium",
        requires_confirmation=True,
        reasons=["destructive_or_financial_change" if high_risk else "formal_plan_change"],
        route="plan_preview",
    )


def _grounding_questions(intent: GroundedIntent) -> list[str]:
    questions: list[str] = []
    if intent.unresolved_activity_mentions:
        questions.append(
            "请从当前行程中明确选择要操作的活动："
            + "、".join(intent.unresolved_activity_mentions)
        )
    if intent.unresolved_place_mentions:
        questions.append(
            "当前候选地点中无法唯一匹配："
            + "、".join(intent.unresolved_place_mentions)
            + "。请先搜索并选择具体地点。"
        )
    return questions


def _reconcile_grounded_ambiguities(intent: GroundedIntent) -> GroundedIntent:
    """Remove ambiguities whose required fact is already grounded."""
    ambiguities = list(intent.ambiguities)
    if intent.target_day_ids:
        ambiguities = [item for item in ambiguities if item != "relative_date_reference_missing"]
    return intent.model_copy(update={"ambiguities": ambiguities})


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
    return re.sub(r"[\s，。！？、·,.!?;；]", "", value.strip().lower())


def _deduplicate(values: list[T]) -> list[T]:
    return list(dict.fromkeys(values))
