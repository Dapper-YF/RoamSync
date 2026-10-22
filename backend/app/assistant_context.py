"""Versioned UI context, deliberately separate from formal write authority.

Persisted in AssistantSession.messages; no new DB owner or memory semantics.
"""
import uuid
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PhysicalLocation(ContextModel):
    city: str | None = Field(default=None, max_length=120)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    coordinate_system: Literal["wgs84", "gcj02"]


class TaskRequirements(ContextModel):
    budget_fen: int | None = Field(default=None, ge=0)
    party_size: int | None = Field(default=None, ge=1, le=100)
    preferences: list[str] = Field(default_factory=list, max_length=20)


class ActionTarget(ContextModel):
    trip_id: uuid.UUID
    expected_version: int = Field(ge=1)
    operation: Literal["plan_trip", "reschedule_trip", "edit_arrangement", "accept_plan"]
    authorization_message_id: uuid.UUID
    revision_id: uuid.UUID | None = None


class RouteReadRequest(ContextModel):
    origin_place_id: uuid.UUID
    destination_place_id: uuid.UUID
    mode: Literal["walk", "driving"] = "walk"


class DiscoveryReadContext(ContextModel):
    city: str | None = Field(default=None, max_length=120)
    query: str = Field(default="", max_length=200)
    category: Literal["all", "attraction", "food", "lodging"] = "all"
    center: PhysicalLocation
    radius_meters: int = Field(default=3000, ge=1, le=50000)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    max_food_price_yuan: float | None = Field(default=None, ge=0)
    include_unknown: bool = True


class ContextEnvelope(ContextModel):
    version: Literal["assistant-context-v1"] = "assistant-context-v1"
    topic_id: str = Field(default="main", min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    surface: Literal["explore", "place", "map", "trip", "assistant", "draft", "execution"] = "assistant"
    physical_location: PhysicalLocation | None = None
    browsing_city: str | None = Field(default=None, max_length=120)
    discussing_place_id: uuid.UUID | None = None
    discussing_place_ids: list[uuid.UUID] = Field(default_factory=list, max_length=8)
    discovery_context: DiscoveryReadContext | None = None
    read_draft_id: uuid.UUID | None = None
    read_draft_version: int | None = Field(default=None, ge=1)
    requirements: TaskRequirements | None = None
    requirement_records: list[dict] = Field(default_factory=list, max_length=200)
    read_trip_id: uuid.UUID | None = None
    action_target: ActionTarget | None = None
    prefer_flexible: bool = False
    preview_action_id: uuid.UUID | None = None
    route_request: RouteReadRequest | None = None
    # Incoming copies are ignored by restore_context; only saved server state wins.
    conversation_memory: dict = Field(default_factory=dict)


def scoped_history(messages: list[dict], topic_id: str) -> list[dict]:
    # Legacy history is only available on the legacy API, never auto-imported
    # into an explicitly scoped topic. Bound state projection as well as prompt.
    return [m for m in messages if isinstance(m.get("context"), dict) and m["context"].get("topic_id") == topic_id][-60:]


def restore_context(incoming: ContextEnvelope, messages: list[dict]) -> tuple[ContextEnvelope, list[dict]]:
    history = scoped_history(messages, incoming.topic_id)
    previous = next((m["context"] for m in reversed(history) if m.get("context")), None)
    if not previous:
        return incoming.model_copy(update={"requirement_records": [], "conversation_memory": {}}), history
    try:
        old = ContextEnvelope.model_validate(previous)
    except ValidationError:
        return incoming.model_copy(update={"requirement_records": [], "conversation_memory": {}}), []
    # A new city starts a new local scope. Explicit null clears a field;
    # omission preserves it while moving between pages in the same topic.
    changed_city = "browsing_city" in incoming.model_fields_set and incoming.browsing_city != old.browsing_city
    changed_trip = "read_trip_id" in incoming.model_fields_set and incoming.read_trip_id != old.read_trip_id
    changed_draft = "read_draft_id" in incoming.model_fields_set and incoming.read_draft_id != old.read_draft_id
    if changed_city or changed_trip or changed_draft:
        history = []
    else:
        # Stop at the last scope transition; older same-topic budgets are not
        # resurrected on the second message after switching cities.
        suffix = []
        for turn in reversed(history):
            saved = turn["context"]
            if (saved.get("browsing_city"), saved.get("read_trip_id"), saved.get("read_draft_id"), (saved.get("conversation_memory") or {}).get("epoch", "")) != (previous.get("browsing_city"), previous.get("read_trip_id"), previous.get("read_draft_id"), (previous.get("conversation_memory") or {}).get("epoch", "")):
                break
            suffix.append(turn)
        history = list(reversed(suffix))
    values = incoming.model_dump()
    values["conversation_memory"] = {} if changed_city or changed_trip or changed_draft else old.conversation_memory
    # State comes from server-persisted prior context, never client-invented
    # source IDs/statuses. Only explicitly global preferences survive a switch.
    from app.requirements import valid_records
    records = valid_records(old.requirement_records)
    values["requirement_records"] = ([r for r in records if r["scope"]["kind"] == "global_preference"]
        if changed_city or changed_trip or changed_draft else records)
    for key in ("browsing_city", "discussing_place_id", "requirements", "read_trip_id", "read_draft_id", "read_draft_version", "discussing_place_ids", "discovery_context"):
        if key not in incoming.model_fields_set and not (changed_city or changed_trip or changed_draft):
            values[key] = getattr(old, key)
    # Never carry a past action authorization or GPS observation forward.
    return ContextEnvelope.model_validate(values), history


def capture_requirements(context: ContextEnvelope, message: str) -> ContextEnvelope:
    """Keep explicit local budget/party answers beyond the short prose window.

    Comparison/query text and formal Trip budgets must not become task inputs.
    """
    if re.search(r"[?？]|吗|是否|适合|行程|旅行|Trip", message, re.I):
        return context
    from app.requirement_language import current_user_evidence_reason, requirement_clauses
    message = "，".join(clause for clause in requirement_clauses(message)
                       if not current_user_evidence_reason(message, clause))
    budget = re.search(r"(?:这次|当前)?预算\s*(?:为|是|在|控制在)?\s*(\d+(?:\.\d{1,2})?)\s*元", message)
    party = re.search(r"(?:我们|一共|人数)?\s*(\d{1,2})\s*(?:个人|人出游|人同行)", message)
    clear_budget = bool(re.search(r"预算不限|不设预算|取消预算", message))
    if not (budget or party or clear_budget):
        return context
    values = (context.requirements or TaskRequirements()).model_dump()
    if budget:
        from decimal import Decimal
        values["budget_fen"] = int(Decimal(budget[1]) * 100)
    if clear_budget:
        values["budget_fen"] = None
    if party and 1 <= int(party[1]) <= 100:
        values["party_size"] = int(party[1])
    return context.model_copy(update={"requirements": TaskRequirements.model_validate(values)})


def capture_effective_requirements(context, message, *, message_id):
    from app.requirements import capture_explicit_requirements
    scope = {"kind": "topic", "topic_id": context.topic_id, "city": context.browsing_city}
    if context.read_draft_id:
        scope = {"kind": "draft", "draft_id": str(context.read_draft_id), "city": context.browsing_city}
    elif context.read_trip_id:
        scope = {"kind": "trip", "trip_id": str(context.read_trip_id), "city": context.browsing_city}
    records = capture_explicit_requirements(context.requirement_records, message,
        scope=scope, source_ref=str(message_id), allow_global_scope=True)
    return context.model_copy(update={"requirement_records": records})


def check_action_target(context: ContextEnvelope, *, session_trip_id, message_id, trip_version, operation):
    target = context.action_target
    if (target is None or target.trip_id != session_trip_id
        or target.authorization_message_id != message_id or target.operation != operation
        or target.expected_version != trip_version):
        raise ValueError("请从目标旅行明确发起操作，并刷新版本后重新授权；读取旅行不会授权修改。")
