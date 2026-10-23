import json
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
_OBJECT_BEFORE_ADD_PATTERN = re.compile(
    r"(?:把|将)\s*([^，。；,;]+?)\s*(?:加入|添加到|放进)\s*(?:当前|这次|正式)?(?:行程|规划|草稿|计划|安排)"
)

_REPLACE_PATTERN = re.compile(
    r"(?:把)?\s*([^，。；,;]+?)\s*(?:换成|替换成|改成)\s*([^，。；,;]+)"
)
_DURATION_VALUE_PATTERN = re.compile(
    r"(?:(?:\d+(?:\.\d+)?|[一二三四五六七八九十百两]+)(?:个)?半?|半)(?:分钟|小时)(?:半|左右)?"
)


def _is_duration_change(match: re.Match) -> bool:
    # A complete measured value changes an attribute, not venue identity.
    # Names containing a duration (e.g. 45分钟咖啡馆) stay in place grounding.
    return bool(_DURATION_VALUE_PATTERN.fullmatch(match.group(2).strip()))


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


class CurrentTurnModification:
    """Only a server-validated current action; all entities are grounded afresh."""
    def __init__(self, place_mentions=()):
        self.place_mentions = list(place_mentions)

    async def extract(self, message, context):
        return SemanticIntentDraft(primary_intent="replan_trip",
            operations=[SemanticIntentOperation(operation="replan_trip", raw_text=message,
                place_mentions=[name for name in self.place_mentions if name in message])],
            confidence=.9, parser="hybrid", parser_version="current-turn-v1")


def restore_current_turn_modification(run, trip_id, message, trip_version):
    """Worker reuse is bound to the persisted run, request and unchanged version.

    Client text/results cannot construct this provider. No saved IDs, dates or
    constraints bypass the resolver; it supplies the already authorized verb.
    """
    if run is None or run.trip_id != trip_id or run.base_trip_version != trip_version or run.user_request != message:
        return None
    try:
        resolution = PlanningIntentResolution.model_validate(run.intent_resolution)
    except (ValueError, TypeError):
        return None
    draft = resolution.semantic_draft
    if (draft is not None and draft.parser == "hybrid" and draft.parser_version == "current-turn-v1"
        and resolution.request.user_request == message and resolution.request.trip_id == trip_id
        and resolution.grounded_intent is not None and resolution.grounded_intent.trip_id == trip_id
        and draft.primary_intent == "replan_trip"
        and [op.operation for op in draft.operations] == ["replan_trip"]
        and all(op.raw_text == message for op in draft.operations)
        and resolution.policy_decision is not None and resolution.policy_decision.route == "plan_preview"):
        return CurrentTurnModification([name for op in draft.operations for name in op.place_mentions if name in message])
    return None


def restore_approved_planning_draft(run, trip_id, message, trip_version, *, preferences_version=None):
    """Replay semantics, never model IDs, only for the matching persisted run."""
    if (run is None or run.trip_id != trip_id or run.base_trip_version != trip_version
            or run.user_request != message):
        return None
    try:
        resolution = PlanningIntentResolution.model_validate(run.intent_resolution)
    except (ValueError, TypeError):
        return None
    draft = resolution.semantic_draft
    if (draft is None or resolution.request.user_request != message or resolution.request.trip_id != trip_id
            or resolution.grounded_intent is None or resolution.grounded_intent.trip_id != trip_id
            or resolution.policy_decision is None or resolution.policy_decision.route not in {"plan_preview", "clarify"}
            or any(op.raw_text not in message or any(name not in op.raw_text for name in
                [*op.place_mentions, *op.activity_mentions]) for op in draft.operations)):
        return None
    trigger = getattr(run, "trigger_snapshot", None)
    if isinstance(trigger, dict) and "prepared_intent" in trigger:
        # This envelope is written only after repository version/policy checks.
        # A present but invalid marker must never fall back to a legacy parser.
        marker = trigger["prepared_intent"]
        if (not isinstance(marker, dict) or type(marker.get("version")) is not int
                or marker["version"] != 1
                or type(marker.get("preferences_version")) is not int
                or marker["preferences_version"] < 1
                or type(marker.get("base_trip_version")) is not int):
            return None
        if preferences_version is not None and marker["preferences_version"] != preferences_version:
            return None
        request = resolution.request
        if any(getattr(run, field, None) != getattr(request, field) for field in
                ("entry_point", "selected_day_id", "selected_activity_id")):
            return None
        expected = {
            "version": 1, "trip_id": str(trip_id), "user_request": message,
            "entry_point": request.entry_point,
            "selected_day_id": str(request.selected_day_id) if request.selected_day_id else None,
            "selected_activity_id": str(request.selected_activity_id) if request.selected_activity_id else None,
            "base_trip_version": trip_version, "preferences_version": marker["preferences_version"],
            "draft": draft.model_dump(mode="json"),
        }
        try:
            matches = json.dumps(marker, sort_keys=True, allow_nan=False) == json.dumps(expected, sort_keys=True)
        except (TypeError, ValueError):
            return None
        if not matches:
            return None
    elif draft.parser != "hybrid" or draft.parser_version != "approved-operation-v2":
        return None
    return draft.model_copy(deep=True)


@dataclass(frozen=True)
class _ActivityEntity:
    id: uuid.UUID
    day_id: uuid.UUID
    day_date: date
    aliases: tuple[str, ...]
    category: str = ""
    scheduled_time: time | None = None
    schedule_locked: bool = False


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
    if any(_is_duration_change(match) for match in _REPLACE_PATTERN.finditer(message)):
        return "modify_day"
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


@dataclass(frozen=True)
class PlanningTripFacts:
    id: uuid.UUID
    destination: str
    start_date: date
    end_date: date
    timezone: str
    version: int


@dataclass(frozen=True)
class PlanningDayFacts:
    id: uuid.UUID
    date: date
    position: int


@dataclass(frozen=True)
class PlanningCandidateFacts:
    id: uuid.UUID
    name: str


@dataclass(frozen=True)
class PlanningIntentSnapshot:
    """Detached facts; safe to retain after closing a read transaction."""
    trip: PlanningTripFacts
    days: tuple[PlanningDayFacts, ...]
    activities: tuple[_ActivityEntity, ...]
    candidates: tuple[PlanningCandidateFacts, ...]
    execution_current_date: date | None = None


async def load_planning_intent_snapshot(
    session: AsyncSession,
    trip_id: uuid.UUID,
    payload: PlanningIntentParseRequest,
) -> PlanningIntentSnapshot:
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
            schedule_locked=activity.schedule_locked,
            aliases=tuple(
                value
                for value in (activity.custom_name, place.name)
                if value
            ),
        )
        for activity, day, place in activity_rows
    ]
    candidate_rows = list(
        (
            await session.scalars(
                select(PlaceCandidate).where(PlaceCandidate.trip_id == trip_id)
            )
        ).all()
    )
    execution = await session.scalar(
        select(TripExecution).where(
            TripExecution.trip_id == trip_id,
            TripExecution.status.in_(("in_progress", "paused")),
        )
    )
    return PlanningIntentSnapshot(
        trip=PlanningTripFacts(trip.id, trip.destination, trip.start_date, trip.end_date, trip.timezone, trip.version),
        days=tuple(PlanningDayFacts(day.id, day.date, day.position) for day in days),
        activities=tuple(entities),
        candidates=tuple(PlanningCandidateFacts(place.id, place.name) for place in candidate_rows),
        execution_current_date=execution.current_date if execution is not None else None,
    )


async def resolve_planning_intent(
    session: AsyncSession,
    trip_id: uuid.UUID,
    payload: PlanningIntentParseRequest,
    *,
    semantic_provider: SemanticIntentProvider | None = None,
    default_planning_intent: PlanningIntentType | None = None,
    prepared_draft: SemanticIntentDraft | None = None,
    clarification_answers: tuple[str, ...] = (),
) -> PlanningIntentResolution:
    """Compatibility adapter; never commit the caller's transaction.

    Network providers must use load_snapshot -> end read transaction ->
    resolve_snapshot at their orchestration boundary. A prepared draft is pure
    data and can be regrounded inside the caller's short write transaction.
    """
    snapshot = await load_planning_intent_snapshot(session, trip_id, payload)
    return await resolve_planning_intent_snapshot(snapshot, payload,
        semantic_provider=semantic_provider, default_planning_intent=default_planning_intent,
        prepared_draft=prepared_draft, clarification_answers=clarification_answers)


async def resolve_planning_intent_snapshot(
    snapshot: PlanningIntentSnapshot,
    payload: PlanningIntentParseRequest,
    *,
    semantic_provider: SemanticIntentProvider | None = None,
    default_planning_intent: PlanningIntentType | None = None,
    prepared_draft: SemanticIntentDraft | None = None,
    clarification_answers: tuple[str, ...] = (),
) -> PlanningIntentResolution:
    """Resolve detached facts, optionally interpreting once outside SQL.

    Supplied operations own semantics; current server facts still own dates,
    identities, missing targets and policy. No model-authored UUID is trusted.
    """
    trip = snapshot.trip
    trip_id = trip.id
    days = list(snapshot.days)
    days_by_id = {day.id: day for day in days}
    days_by_date = {day.date: day for day in days}
    entities = list(snapshot.activities)
    entities_by_id = {entity.id: entity for entity in entities}
    candidate_rows = list(snapshot.candidates)

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
    intent_type = "unknown"
    scope_operations = []
    if prepared_draft is not None:
        if any(op.raw_text not in payload.message for op in prepared_draft.operations):
            raise ValueError("prepared_intent_source_mismatch")
        operations = {op.operation for op in prepared_draft.operations}
        intent_type = ("create_plan" if "create_plan" in operations else
                       "replan_trip" if "replan_trip" in operations else
                       "modify_day" if operations & {"add_activity", "remove_activity", "replace_activity",
                           "reorder_activities", "optimize_route", "adjust_budget", "weather_replan"} else "unknown")
        scope_operations = [op for op in prepared_draft.operations
            if op.operation not in {"query_trip", "search_places", "general_chat", "unsupported"}] or prepared_draft.operations
    else:
        intent_type = classify_planning_intent(
            scope_message, has_activities=bool(entities),
            has_selected_day=payload.selected_day_id is not None,
            has_selected_activity=payload.selected_activity_id is not None,
        )
    # run_type is UI context, never authorization to turn arbitrary text into a plan.
    ambiguities: list[str] = []
    missing_fields: list[str] = []
    target_day: DayPlan | None = None
    local_today = datetime.now(ZoneInfo(trip.timezone)).date()
    relative_date_base = (
        snapshot.execution_current_date
        if snapshot.execution_current_date is not None
        else local_today if trip.start_date <= local_today <= trip.end_date else None
    )
    scope = _parse_time_scope(
        scope_message, trip, days, ambiguities, relative_date_base=relative_date_base
    ) if prepared_draft is None else None
    if prepared_draft is not None:
        # Scope belongs to the actual operation clause, never an earlier
        # consultation about another day. Unsupported multi-day local writes
        # clarify atomically instead of executing just their first operation.
        operation_scopes = [_parse_time_scope(_without_trip_date_range(op.raw_text, trip)[0],
            trip, days, ambiguities, relative_date_base=relative_date_base) for op in scope_operations]
        ui_day = (days_by_id[payload.selected_day_id] if payload.selected_day_id is not None else
                  days_by_id[entities_by_id[payload.selected_activity_id].day_id]
                  if payload.selected_activity_id is not None else None)
        # An unscoped operation refers to its UI selection, not a date borrowed
        # from a different clause. Reconcile those targets before merging scope.
        if intent_type == "modify_day":
            operation_scopes = [_scope_for_day(ui_day, days, item)
                if ui_day is not None and (item is None or
                    (item.day_date is None and item.day_number is None)) else item
                for item in operation_scopes]
            if len(operation_scopes) > 1 and any(item is None or
                    (item.day_date is None and item.day_number is None) for item in operation_scopes):
                missing_fields.append("target_day")
        operation_scopes = [item for item in operation_scopes if item is not None]
        day_scopes = {(item.day_date, item.day_number) for item in operation_scopes
                      if item.day_date is not None or item.day_number is not None}
        if len(day_scopes) > 1:
            ambiguities.append("multiple_operation_days")
        elif operation_scopes:
            scope = next((item for item in operation_scopes if item.day_date is not None
                or item.day_number is not None), operation_scopes[0])
            periods = {item.period for item in operation_scopes if item.period is not None}
            if len(periods) > 1:
                scope = scope.model_copy(update={"period": "full_day"})
            elif periods:
                scope = scope.model_copy(update={"period": next(iter(periods))})
    if prepared_draft is None and names_full_range and scope is None and intent_type != "unknown":
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
        trip_start_date=trip.start_date,
    )
    if target_day is None and protected_activity_ids and intent_type not in {"create_plan", "replan_trip"}:
        protected_days = {
            entities_by_id[activity_id].day_id for activity_id in protected_activity_ids
        }
        if len(protected_days) == 1:
            target_day = days_by_id[protected_days.pop()]
            scope = _scope_for_day(target_day, days, scope)

    if (intent_type == "modify_day" and target_day is None and clarification_answers
            and not ambiguities and (scope is None or
                (scope.day_date is None and scope.day_number is None))):
        # Answers fill only a missing target. They never enter operation parsing,
        # entity extraction, constraints, source text, or the persisted draft.
        answer_ambiguities: list[str] = []
        answer_scope = _parse_time_scope(clarification_answers[-1], trip, days,
            answer_ambiguities, relative_date_base=relative_date_base)
        if answer_scope is not None and not answer_ambiguities:
            target_day = days_by_date.get(answer_scope.day_date)
            if target_day is not None:
                scope = _scope_for_day(target_day, days, scope)
                missing_fields = [field for field in missing_fields if field != "target_day"]

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
    semantic_draft = prepared_draft or _build_rule_semantic_draft(payload.message, intent_type, scope, scope_message=scope_message)
    if (
        prepared_draft is None and semantic_provider is not None
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
        # Remove preservation references before choosing a mutation date.
        # They may share a clause with an actual change request.
        part = re.sub(r"(?:保留|保持|维持|沿用)(?:其他|其余|剩余)(?:的)?(?:日期|天|日)(?:的)?(?:行程|安排|活动)?(?:不变|照旧|不要动|别动)?", "", part)
        part = re.sub(r"(?:保留)?第[一二三四五六七八九十两\d]+天(?:的)?\d{1,2}(?:点|时)(?:\d{1,2}分?)?(?:的)?(?:固定|锁定|预约)(?:的)?活动(?:不要动|别动|不变|照旧)?", "", part)
        if not part.strip():
            continue
        boundary = re.search(r"不变|照旧|不调整|不要改动|不要动|别动", part)
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
    if re.fullmatch(r"(?:总|每日|每天|旅行|行程)?预算(?:上限)?[￥¥]?[\d零〇一二三四五六七八九十百千万两]+(?:\.\d{1,2})?(?:元|块钱)?", value):
        return "budget_value"
    calendar = r"(?:\d{4}年)?\d{1,2}月\d{1,2}日|\d{4}-\d{2}-\d{2}"
    if re.fullmatch(rf"(?:出发|返程|旅行|行程|开始|结束)?日期(?:{calendar})(?:(?:至|到|—)(?:{calendar}))?", value):
        return "trip_setting"
    if re.fullmatch(r"(?:[\d一二三四五六七八九十两]+(?:个)?人)(?:出行|旅行)", value):
        return "trip_setting"
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
    trip_start_date: date | None = None,
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
        # Regex captures are not identities. Discard format-only fragments
        # before substring matching (empty strings would match every alias).
        # Remove boundary decoration, not punctuation inside a real name.
        normalized_mention = _normalize_entity(mention).strip('()（）[]【】{}「」『』“”‘’"\'：:*-•')
        if not any(char.isalpha() for char in normalized_mention):
            continue
        fixed = _resolve_fixed_activity_reference(normalized_mention, entities, trip_start_date)
        if fixed is not None:
            if len(fixed) == 1:
                resolved.append(fixed[0])
            elif not fixed:
                ambiguities.append(f"activity_not_found:{mention}")
            else:
                ambiguities.append(f"activity_not_unique:{mention}")
            continue
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


def _resolve_fixed_activity_reference(value: str, entities: list[_ActivityEntity], trip_start_date: date | None) -> list[uuid.UUID] | None:
    """Ground a dated locked appointment by persisted day and clock time."""
    weekday = re.fullmatch(r"(?:周|星期)([一二三四五六日天])(?:的)?(上午|下午|晚上)?(?:的)?(?:固定|锁定|预约)(?:的)?(?:活动)?", value)
    if weekday:
        index = '一二三四五六日'.index(weekday[1].replace('天', '日'))
        period = weekday[2]
        bounds = {'上午': (0, 12), '下午': (12, 18), '晚上': (18, 24)}
        return [e.id for e in entities if e.schedule_locked and e.day_date.weekday() == index
            and (not period or e.scheduled_time and bounds[period][0] <= e.scheduled_time.hour < bounds[period][1])]
    match = re.fullmatch(r"第([一二三四五六七八九十两\d]+)天(?:的)?(\d{1,2})(?:点|时)(?:(\d{1,2})分?)?(?:的)?(?:固定|锁定|预约)(?:的)?活动", value)
    if match is None:
        return None
    day_number, hour = _parse_chinese_number(match[1]), int(match[2])
    minute = int(match[3]) if match[3] is not None else None
    if day_number < 1 or hour > 23 or (minute is not None and minute > 59):
        return []
    if trip_start_date is None:
        return []
    target_date = trip_start_date + timedelta(days=day_number - 1)
    return [entity.id for entity in entities if entity.day_date == target_date
            and entity.scheduled_time is not None and entity.scheduled_time.hour == hour
            and (minute is None or entity.scheduled_time.minute == minute)
            and entity.schedule_locked]


def _is_plan_meta_activity_reference(value: str) -> bool:
    """Ignore ungrounded plan properties captured as if they were activity names."""
    if re.fullmatch(r"(?:已完成|已经完成|正在进行|执行中)(?:的)?活动", value):
        # Persisted execution state owns these groups; they are not venue names.
        return True
    if re.fullmatch(r"(?:其他|其余|剩余|非目标)(?:的)?(?:日期|天|日)(?:的)?(?:行程|安排|活动)?(?:不变|照旧)?", value):
        return True
    if re.fullmatch(r"第[一二三四五六七八九十两\d]+天(?:的)?(?:安排|行程)?", value):
        return True
    if value in {"顺序", "时长", "时间", "交通", "交通衔接", "安排", "内容", "要求", "上述要求", "留白", "空闲", "自由时间"}:
        return True
    if re.fullmatch(r"(?:用户)?(?:整体)?偏好[:：][\d一二三四五六七八九十两]+(?:个)?人(?:出行|旅行)", value):
        return True
    # Exact generic preference labels observed in the real creation→revision
    # handoff. A named venue still resolves above; unknown names still clarify.
    if re.fullmatch(r"(?:喜欢|偏好)?(?:历史文化|老街巷|本地小吃)(?:的)?(?:偏好|兴趣)?", value):
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
    for match in _OBJECT_BEFORE_ADD_PATTERN.finditer(message):
        if re.search(r"(?:不|别|不要|无需|不必|不再|无须)\s*$", message[:match.start()]):
            continue
        values.extend(_split_coordinated_mentions(match.group(1)))
    for pattern in _PLACE_PATTERNS:
        for match in pattern.finditer(message):
            # An explicit prohibition is not a request to add that place.
            if re.search(r"(?:不|别|不要|无需|不必|不再|无须)\s*$", message[:match.start()]):
                continue
            values.extend(_split_coordinated_mentions(match.group(1)))
    return _deduplicate([value for value in values if value and not is_generic_place_quantity(value)
                         and not _is_non_place_reference(value)])


def _is_non_place_reference(value: str) -> bool:
    """Classify complete plan/requirement references, never a venue substring."""
    normalized = _normalize_entity(value)
    if re.fullmatch(r"(?:到|进)?(?:当前|这次|正式)?(?:行程|规划|草稿|计划|安排|候选)", normalized):
        return True
    if _trip_setting_kind(normalized) or _is_plan_meta_activity_reference(normalized):
        return True
    day = r"(?:第[一二三四五六七八九十两\d]+天|\d{4}-\d{1,2}-\d{1,2})"
    prefix = rf"(?:(?:{day})(?:的)?)?"
    state = r"(?:(?:已|已经|此前|之前)?(?:撤销|取消|废止|失效)(?:的)?|不再适用的?)?"
    dimension = r"(?:步行|走路)(?:时间|距离)?(?:上限|限制|要求|偏好)|(?:每日|每天|总)?预算(?:上限|限制|要求)|(?:节奏|拍照|摄影|天气)(?:要求|偏好|限制)"
    return bool(re.fullmatch(prefix + state + dimension + r"(?:不再适用|已撤销)?", normalized))


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

    all_replacements = list(_REPLACE_PATTERN.finditer(message))
    duration_matches = [match for match in all_replacements if _is_duration_change(match)]
    replace_matches = [match for match in all_replacements if not _is_duration_change(match)]
    if duration_matches:
        add_operation("replan_trip", activity_mentions=[match.group(1).strip() for match in duration_matches])
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
        if _trip_setting_kind(part) != "budget" and not (
            _trip_setting_kind(part) == "budget_value" and
            re.match(r"\s*(?:请)?(?:保留|保持|维持|沿用)", clause)
        )
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
    # Protection is a prohibition, never an authorization to edit that activity
    # or the other activities on its date. The request keeps protection separately.
    target_activity_ids = [selected_activity_id] if (selected_activity_id is not None
        and target_day is not None and selected_activity_id not in protected_activity_ids) else []
    unresolved_activities: list[str] = []
    candidate_place_ids: list[uuid.UUID] = []
    unresolved_places: list[str] = []
    entity_by_id = {entity.id: entity for entity in entities}

    activity_mentions = _deduplicate(
        [mention for operation in draft.operations for mention in operation.activity_mentions]
    )
    for mention in activity_mentions:
        if is_generic_place_quantity(mention) or _trip_setting_kind(mention) or _is_plan_meta_activity_reference(_normalize_entity(mention)):
            continue
        normalized = _normalize_entity(mention)
        if normalized in {"这个", "这个活动", "这个地方", "它", "该活动", "那个景点"}:
            if selected_activity_id is not None:
                if selected_activity_id not in protected_activity_ids:
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
            if matches[0] not in protected_activity_ids:
                target_activity_ids.append(matches[0])
        else:
            unresolved_activities.append(mention)

    place_mentions = _deduplicate(
        [mention for operation in draft.operations for mention in operation.place_mentions]
    )
    for mention in place_mentions:
        if is_generic_place_quantity(mention) or _is_non_place_reference(mention):
            continue
        normalized = _normalize_entity(mention)
        # Existing formal activity identity wins over destination research.
        existing_matches = [entity.id for entity in entities
                            if (target_day is None or entity.day_id == target_day.id)
                            and (mention == str(entity.id) or any(normalized == _normalize_entity(alias) for alias in entity.aliases))]
        if len(existing_matches) == 1:
            if existing_matches[0] not in protected_activity_ids:
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
            if target_day is not None and entity.day_id != target_day.id:
                inherited_ambiguities.append(f"activity_outside_target_day:{entity.id}")
            elif target_day is None:
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
        elif ambiguity == "multiple_operation_days":
            questions.append("这次局部调整涉及多个日期，暂未生成候选。请先选择一个日期，我会保留其余要求继续处理。")
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
