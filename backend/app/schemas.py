import uuid
from datetime import date, datetime, time
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ExpenseCategory = Literal["food", "transport", "ticket", "lodging", "shopping", "other"]
TripPace = Literal["relaxed", "balanced", "intensive"]
InterestCategory = Literal[
    "history", "culture", "nature", "food", "photography", "shopping", "family", "nightlife"
]
PreferenceTransportMode = Literal["walk", "transit", "driving"]
PlanningIntentType = Literal["create_plan", "replan_trip", "modify_day", "unknown"]
PlanningDayPeriod = Literal["morning", "afternoon", "evening", "full_day"]
PlanningIntentEntryPoint = Literal["trip_planner", "day_planner", "activity_editor"]
TravelGoalType = Literal[
    "travel_chat", "destination_exploration", "destination_discovery", "travel_advice",
    "comparison", "recommendation", "explanation", "trip_planning", "trip_modification",
    "replan", "trip_execution",
]
TravelGoalRuntime = Literal["companion", "planning", "execution"]
IntentPrimary = Literal[
    "create_plan",
    "replan_trip",
    "create_trip",
    "query_trip",
    "search_places",
    "add_activity",
    "remove_activity",
    "replace_activity",
    "reorder_activities",
    "optimize_route",
    "adjust_budget",
    "weather_replan",
    "booking_assistance",
    "general_chat",
    "unsupported",
]
IntentOperationType = Literal[
    "create_plan",
    "replan_trip",
    "query_trip",
    "search_places",
    "add_activity",
    "remove_activity",
    "replace_activity",
    "reorder_activities",
    "optimize_route",
    "adjust_budget",
    "weather_replan",
    "booking_assistance",
    "general_chat",
    "unsupported",
]
IntentOperationMode = Literal["answer_only", "preview_change", "clarify", "reject"]
IntentRiskLevel = Literal["low", "medium", "high", "prohibited"]


class TravelGoalRouting(BaseModel):
    """Compact, auditable routing result; signals are labels, never model reasoning."""

    model_config = ConfigDict(extra="forbid")

    goal_type: TravelGoalType
    confidence: float = Field(ge=0, le=1)
    target_runtime: TravelGoalRuntime
    mutation_requested: bool
    trip_context_required: bool
    knowledge_required: bool
    live_fact_likely_required: bool
    referenced_entities: list[str] = Field(default_factory=list, max_length=20)
    referenced_previous_decision: bool = False
    clarification_needed: bool = False
    signals: list[str] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_boundary(self) -> "TravelGoalRouting":
        expected = ("planning" if self.goal_type in {"trip_planning", "trip_modification", "replan"}
                    else "execution" if self.goal_type == "trip_execution" else "companion")
        if self.target_runtime != expected:
            raise ValueError("goal_type and target_runtime disagree")
        if self.mutation_requested and self.target_runtime != "planning":
            raise ValueError("only planning goals can request itinerary mutation")
        return self


class IntentConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_must_not_increase: bool = False
    max_additional_cost_fen: int | None = Field(default=None, ge=0)
    preferred_environment: Literal["indoor", "outdoor"] | None = None
    max_walking_minutes: int | None = Field(default=None, ge=0, le=1440)
    requested_pace: TripPace | None = None
    weather_sensitive: bool = False
    preserve_completed: bool = True


class SemanticIntentOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: IntentOperationType
    raw_text: str = Field(min_length=1, max_length=4000)
    date_expression: str | None = Field(default=None, max_length=100)
    period: PlanningDayPeriod | None = None
    activity_mentions: list[str] = Field(default_factory=list, max_length=20)
    place_mentions: list[str] = Field(default_factory=list, max_length=20)
    constraints: IntentConstraints = Field(default_factory=IntentConstraints)


class SemanticIntentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_intent: IntentPrimary
    operations: list[SemanticIntentOperation] = Field(min_length=1, max_length=10)
    confidence: float = Field(ge=0, le=1)
    missing_fields: list[str] = Field(default_factory=list, max_length=20)
    ambiguities: list[str] = Field(default_factory=list, max_length=20)
    parser: Literal["rules", "model", "hybrid"] = "rules"
    parser_version: str = Field(min_length=1, max_length=40)


class GroundedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trip_id: uuid.UUID
    primary_intent: IntentPrimary
    operation_types: list[IntentOperationType] = Field(min_length=1, max_length=10)
    target_day_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    target_activity_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    candidate_place_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    unresolved_activity_mentions: list[str] = Field(default_factory=list, max_length=20)
    unresolved_place_mentions: list[str] = Field(default_factory=list, max_length=20)
    constraints: IntentConstraints = Field(default_factory=IntentConstraints)
    missing_fields: list[str] = Field(default_factory=list, max_length=20)
    ambiguities: list[str] = Field(default_factory=list, max_length=20)


class IntentPolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_mode: IntentOperationMode
    risk_level: IntentRiskLevel
    requires_confirmation: bool
    reasons: list[str] = Field(default_factory=list, max_length=20)
    route: Literal["clarify", "answer", "plan_preview", "reject"]


class PlanningTimeScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day_number: int | None = Field(default=None, ge=1)
    day_date: date | None = None
    period: PlanningDayPeriod | None = None


class PlanningIntent(BaseModel):
    """Strict output contract shared by rule parsing and future model fallback."""

    model_config = ConfigDict(extra="forbid")

    intent_type: PlanningIntentType
    source_text: str = Field(max_length=4000)
    time_scope: PlanningTimeScope | None = None
    protected_activity_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    requested_place_queries: list[str] = Field(default_factory=list, max_length=20)
    requested_pace: TripPace | None = None
    missing_fields: list[str] = Field(default_factory=list, max_length=20)
    ambiguities: list[str] = Field(default_factory=list, max_length=20)


class PlanningRequest(BaseModel):
    """Resolved command handed from intent parsing to a planning graph."""

    model_config = ConfigDict(extra="forbid")

    trip_id: uuid.UUID
    user_request: str = Field(max_length=4000)
    intent: PlanningIntent
    entry_point: PlanningIntentEntryPoint = "trip_planner"
    selected_day_id: uuid.UUID | None = None
    selected_activity_id: uuid.UUID | None = None
    target_day_id: uuid.UUID | None = None


class PlanningIntentParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    entry_point: PlanningIntentEntryPoint = "trip_planner"
    selected_day_id: uuid.UUID | None = None
    selected_activity_id: uuid.UUID | None = None

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message cannot be blank")
        return normalized


class PlanningIntentResolution(BaseModel):
    request: PlanningRequest
    requires_clarification: bool
    clarification_questions: list[str] = Field(default_factory=list, max_length=20)
    parser_version: Literal["rules-v1"] = "rules-v1"
    semantic_draft: SemanticIntentDraft | None = None
    grounded_intent: GroundedIntent | None = None
    policy_decision: IntentPolicyDecision | None = None


class TripCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    destination: str = Field(default="", max_length=120)
    destination_adcode: str = Field(default="", max_length=12)
    destination_citycode: str = Field(default="", max_length=12)
    center_longitude: float | None = Field(default=None, ge=-180, le=180)
    center_latitude: float | None = Field(default=None, ge=-90, le=90)
    accommodation: str = Field(default="", max_length=240)
    accommodation_poi_id: str = Field(default="", max_length=80)
    accommodation_address: str = Field(default="", max_length=300)
    accommodation_district: str = Field(default="", max_length=120)
    accommodation_longitude: float | None = Field(default=None, ge=-180, le=180)
    accommodation_latitude: float | None = Field(default=None, ge=-90, le=90)
    start_date: date
    end_date: date
    total_budget_fen: int | None = Field(default=None, gt=0)
    daily_budget_fen: int | None = Field(default=None, gt=0)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    timezone: str = Field(default="Asia/Shanghai", max_length=64)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("unknown IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_trip_constraints(self) -> "TripCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.total_budget_fen is None) != (self.daily_budget_fen is None):
            raise ValueError("total and daily budget must be set together")
        if self.daily_budget_fen is not None and self.daily_budget_fen > self.total_budget_fen:
            raise ValueError("daily_budget_fen cannot exceed total_budget_fen")
        return self


class TripResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    destination: str
    destination_adcode: str
    destination_citycode: str
    center_longitude: float | None
    center_latitude: float | None
    accommodation: str
    accommodation_poi_id: str
    accommodation_address: str
    accommodation_district: str
    accommodation_longitude: float | None
    accommodation_latitude: float | None
    start_date: date
    end_date: date
    total_budget_fen: int | None
    daily_budget_fen: int | None
    currency: str
    timezone: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    version: int
    status: Literal["upcoming", "active", "completed", "archived"]


class TripUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    destination: str | None = Field(default=None, min_length=1, max_length=120)
    destination_adcode: str | None = Field(default=None, max_length=12)
    destination_citycode: str | None = Field(default=None, max_length=12)
    center_longitude: float | None = Field(default=None, ge=-180, le=180)
    center_latitude: float | None = Field(default=None, ge=-90, le=90)
    accommodation: str | None = Field(default=None, max_length=240)
    accommodation_poi_id: str | None = Field(default=None, max_length=80)
    accommodation_address: str | None = Field(default=None, max_length=300)
    accommodation_district: str | None = Field(default=None, max_length=120)
    accommodation_longitude: float | None = Field(default=None, ge=-180, le=180)
    accommodation_latitude: float | None = Field(default=None, ge=-90, le=90)
    start_date: date | None = None
    end_date: date | None = None
    total_budget_fen: int | None = Field(default=None, gt=0)
    daily_budget_fen: int | None = Field(default=None, gt=0)
    version: int = Field(ge=1)
    confirm_day_removal: bool = False


class TripPreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    trip_id: uuid.UUID
    pace: TripPace
    interest_categories: list[InterestCategory]
    transport_modes: list[PreferenceTransportMode]
    daily_start_time: time
    daily_end_time: time
    meal_preferences: str
    avoid_categories: list[str]
    max_walking_minutes: int
    free_text_requirements: str
    requirement_records: list[dict] = Field(default_factory=list)
    version: int
    created_at: datetime
    updated_at: datetime


class TripPreferencesUpdate(BaseModel):
    version: int = Field(ge=1)
    pace: TripPace
    interest_categories: list[InterestCategory] = Field(max_length=8)
    transport_modes: list[PreferenceTransportMode] = Field(min_length=1, max_length=3)
    daily_start_time: time
    daily_end_time: time
    meal_preferences: str = Field(default="", max_length=500)
    avoid_categories: list[str] = Field(default_factory=list, max_length=12)
    max_walking_minutes: int = Field(gt=0, le=480)
    free_text_requirements: str = Field(default="", max_length=2000)

    @field_validator("interest_categories", "transport_modes", "avoid_categories")
    @classmethod
    def require_unique_items(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("list items must be unique")
        return value

    @field_validator("meal_preferences", "free_text_requirements")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("avoid_categories")
    @classmethod
    def normalize_avoid_categories(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("avoid_categories items must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_daily_window(self) -> "TripPreferencesUpdate":
        if self.daily_end_time <= self.daily_start_time:
            raise ValueError("daily_end_time must be after daily_start_time")
        return self


class LocationPoiResponse(BaseModel):
    poi_id: str
    name: str
    address: str
    district: str
    longitude: float
    latitude: float
    type_name: str
    rating: float | None = None


class TripDeletionPreviewResponse(BaseModel):
    trip_id: uuid.UUID
    day_plans: int
    activities: int
    candidates: int
    expenses: int


class TripArchiveResponse(BaseModel):
    trip_id: uuid.UUID
    status: Literal["archived"]


class CitySuggestionResponse(BaseModel):
    name: str
    adcode: str
    citycode: str
    longitude: float
    latitude: float


class ExpenseCreate(BaseModel):
    idempotency_key: uuid.UUID
    amount_fen: int = Field(gt=0)
    category: ExpenseCategory
    description: str = Field(min_length=1, max_length=500)
    spent_at: datetime | None = None

    @field_validator("spent_at")
    @classmethod
    def validate_spent_at(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("spent_at must include a timezone offset")
        return value


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trip_id: uuid.UUID
    idempotency_key: uuid.UUID
    amount_fen: int
    category: str
    description: str
    spent_at: datetime
    created_at: datetime
    duplicate: bool = False


class BudgetResponse(BaseModel):
    trip_id: uuid.UUID
    currency: str
    total_budget_fen: int | None
    total_spent_fen: int
    total_remaining_fen: int | None
    daily_budget_fen: int | None
    today_spent_fen: int
    today_remaining_fen: int | None
    local_date: date


class HealthResponse(BaseModel):
    status: Literal["ok", "ready"]


ActivityStatus = Literal["planned", "active", "completed", "skipped"]
PlaceCategory = Literal["sight", "food", "culture", "nature", "shopping"]
Confidence = Literal["high", "medium", "low"]


class SourceRecordResponse(BaseModel):
    id: uuid.UUID
    title: str
    url: str
    provider: str
    queried_at: datetime
    confidence: Confidence


class PlaceCandidateResponse(BaseModel):
    id: uuid.UUID
    name: str
    category: PlaceCategory
    neighborhood: str
    description: str
    longitude: float
    latitude: float
    suggested_duration_minutes: int
    estimated_cost_fen: int
    rating: float
    tags: list[str]
    source: SourceRecordResponse


class PlaceSearchResultResponse(BaseModel):
    provider: Literal["amap"] = "amap"
    provider_place_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=160)
    category: PlaceCategory
    neighborhood: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=500)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    suggested_duration_minutes: int = Field(gt=0, le=1440)
    estimated_cost_fen: int = Field(ge=0)
    rating: float = Field(default=0, ge=0, le=5)
    tags: list[str] = Field(default_factory=list, max_length=12)
    source_url: str = Field(max_length=500)

    @field_validator("source_url")
    @classmethod
    def require_amap_source_url(cls, value: str) -> str:
        if not value.startswith("https://www.amap.com/"):
            raise ValueError("source_url must be an AMap HTTPS URL")
        return value


class ActivityResponse(BaseModel):
    id: uuid.UUID
    place_id: uuid.UUID
    name: str
    custom_name: str | None = None
    display_name: str
    category: PlaceCategory
    neighborhood: str
    longitude: float
    latitude: float
    scheduled_time: time
    duration_minutes: int
    importance: Literal["low", "normal", "high", "must_do"]
    can_skip: bool
    minimum_duration_minutes: int | None
    importance_source: Literal["user_explicit", "user_confirmed", "system_default", "unknown"]
    can_skip_source: Literal["user_explicit", "user_confirmed", "system_default", "unknown"]
    minimum_duration_source: Literal["user_explicit", "user_confirmed", "system_default", "unknown"]
    estimated_cost_fen: int
    status: ActivityStatus
    position: int
    schedule_locked: bool
    version: int
    note: str | None = None
    updated_at: datetime
    source: SourceRecordResponse


RouteMode = Literal["walk", "transit", "driving"]


class RouteAlternativeResponse(BaseModel):
    distance_meters: int
    duration_minutes: int
    path: list[tuple[float, float]]


class RouteLegResponse(BaseModel):
    id: uuid.UUID
    from_activity_id: uuid.UUID
    to_activity_id: uuid.UUID
    position: int
    mode: RouteMode
    distance_meters: int
    duration_minutes: int
    provider: str
    is_estimated: bool
    path: list[tuple[float, float]] = []
    alternatives: list[RouteAlternativeResponse] = []


class ScheduleConflictResponse(BaseModel):
    activity_id: uuid.UUID
    code: Literal["late_finish"]
    message: str


class DayPlanResponse(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    date: date
    label: str
    theme: str
    position: int
    route_mode: RouteMode = "walk"
    activities: list[ActivityResponse]
    route_legs: list[RouteLegResponse] = []
    conflicts: list[ScheduleConflictResponse] = []


class ActivityCreate(BaseModel):
    place_id: uuid.UUID | None = None
    place_snapshot: PlaceSearchResultResponse | None = None
    importance: Literal["low", "normal", "high", "must_do"] = "normal"
    can_skip: bool = True
    minimum_duration_minutes: int | None = Field(default=None, ge=1, le=1440)

    @model_validator(mode="after")
    def require_exactly_one_place(self) -> "ActivityCreate":
        if (self.place_id is None) == (self.place_snapshot is None):
            raise ValueError("provide exactly one of place_id or place_snapshot")
        if self.importance == "must_do":
            if "can_skip" in self.model_fields_set and self.can_skip:
                raise ValueError("must_do activity cannot be skippable")
            self.can_skip = False
        return self


class ActivityUpdate(BaseModel):
    version: int = Field(gt=0)
    custom_name: str | None = Field(default=None, max_length=160)
    scheduled_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    importance: Literal["low", "normal", "high", "must_do"] | None = None
    can_skip: bool | None = None
    minimum_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    estimated_cost_fen: int | None = Field(default=None, ge=0)
    status: ActivityStatus | None = None
    note: str | None = Field(default=None, max_length=2000)
    schedule_locked: bool | None = None

    @field_validator("custom_name", "note")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_an_edit(self) -> "ActivityUpdate":
        if not (self.model_fields_set - {"version"}):
            raise ValueError("at least one editable field is required")
        return self


class ActivityMoveRequest(BaseModel):
    version: int = Field(gt=0)
    target_day_plan_id: uuid.UUID
    target_position: int = Field(ge=0)


class ActivityMoveResponse(BaseModel):
    activity_id: uuid.UUID
    source_day: DayPlanResponse
    target_day: DayPlanResponse


class ActivityOrderUpdate(BaseModel):
    activity_ids: list[uuid.UUID]


class RouteRecalculateRequest(BaseModel):
    mode: RouteMode = "walk"


class PlanningBudgetDayResponse(BaseModel):
    day_plan_id: uuid.UUID
    date: date
    planned_fen: int
    remaining_fen: int | None
    ratio: float | None
    status: Literal["comfortable", "watch", "over", "unconstrained"]


class PlanningBudgetResponse(BaseModel):
    trip_id: uuid.UUID
    total_planned_fen: int
    total_remaining_fen: int | None
    days: list[PlanningBudgetDayResponse]


GoalStatus = Literal["satisfied", "unsatisfied", "partially_satisfied", "not_evaluable"]


class PlanningHardGoals(BaseModel):
    end_before: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    max_walking_minutes: int | None = Field(default=None, ge=0, le=1440)


class PlanningSoftGoals(BaseModel):
    pace: TripPace | None = None
    minimize_walking: bool = False
    preserve_existing: bool = False


class PlanningGoals(BaseModel):
    """Request-scoped decision state, not a change to the formal itinerary."""
    target_days: list[str] = Field(default_factory=list)
    hard_goals: PlanningHardGoals = Field(default_factory=PlanningHardGoals)
    soft_goals: PlanningSoftGoals = Field(default_factory=PlanningSoftGoals)


class GoalSatisfactionItem(BaseModel):
    goal: str
    type: Literal["hard", "soft"]
    status: GoalStatus
    evidence: dict = Field(default_factory=dict)


class GoalSatisfactionResult(BaseModel):
    results: list[GoalSatisfactionItem] = Field(default_factory=list)


class PlanningContextResponse(BaseModel):
    trip: TripResponse
    preferences: TripPreferencesResponse
    days: list[DayPlanResponse]
    candidates: list[PlaceCandidateResponse]
    actual_budget: BudgetResponse
    planning_budget: PlanningBudgetResponse
    generated_at: datetime
    external_facts: dict = Field(default_factory=dict)
    execution_recovery: dict | None = None
    planning_goals: PlanningGoals | None = None
    formal_route_facts: dict = Field(default_factory=dict)
    effective_requirements: list[dict] = Field(default_factory=list)


PlanningRunType = Literal["initial_plan", "replan"]
PlanningRunStatus = Literal[
    "queued", "researching", "awaiting_clarification", "planning", "validating", "awaiting_confirmation",
    "accepted", "rejected", "failed", "cancelled", "answered"
]
PlanRevisionStatus = Literal["pending", "accepted", "rejected", "superseded"]
PlanningRunErrorCode = Literal[
    "planner_not_configured",
    "planner_authentication_failed",
    "planner_permission_denied",
    "planner_rate_limited",
    "planner_timeout",
    "planner_unavailable",
    "planner_incomplete_output",
    "planner_invalid_output",
    "planner_provider_error",
    "planner_request_rejected",
    "planner_constraints_unsatisfied",
    "goal_constraints_unsatisfied",
    "decision_context_invalid",
    "planner_map_unavailable",
    "planner_requested_place_unresolved",
    "planner_search_authentication_failed",
    "planner_research_unavailable",
    "planner_research_incomplete_output",
    "planner_research_invalid_output",
    "planning_run_timeout",
    "planning_graph_failed",
]


class PlanningClarificationInterrupt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["clarification"]
    questions: list[str] = Field(min_length=1, max_length=20)
    run_id: uuid.UUID


class PlanningApprovalInterrupt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["approval"]
    run_id: uuid.UUID
    revision_id: uuid.UUID


PlanningPendingInterrupt = Annotated[
    PlanningClarificationInterrupt | PlanningApprovalInterrupt,
    Field(discriminator="kind"),
]


class PlanningRunCreate(BaseModel):
    run_type: PlanningRunType = "initial_plan"
    user_request: str = Field(min_length=1, max_length=4000)
    entry_point: PlanningIntentEntryPoint = "trip_planner"
    selected_day_id: uuid.UUID | None = None
    selected_activity_id: uuid.UUID | None = None
    disruption_event_id: uuid.UUID | None = None

    @field_validator("user_request")
    @classmethod
    def normalize_request(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("user_request cannot be blank")
        return normalized


class PlanningRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trip_id: uuid.UUID
    disruption_event_id: uuid.UUID | None = None
    trigger_type: str | None = None
    trigger_fingerprint: str | None = None
    trigger_snapshot: dict | None = None
    run_type: PlanningRunType
    status: PlanningRunStatus
    user_request: str
    response_text: str | None = None
    progress: dict | None = None
    heartbeat_at: datetime | None = None
    entry_point: PlanningIntentEntryPoint
    selected_day_id: uuid.UUID | None
    selected_activity_id: uuid.UUID | None
    intent_resolution: PlanningIntentResolution | None
    base_trip_version: int
    model_provider: str | None
    model_name: str | None
    token_usage: int
    error_code: PlanningRunErrorCode | None
    error_message: str | None
    error_details: dict | None = None
    pending_interrupt: PlanningPendingInterrupt | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class PlanningRunDecision(BaseModel):
    decision: Literal["clarify", "accept", "reject"]
    answer: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def require_clarification_answer(self) -> "PlanningRunDecision":
        if self.decision == "clarify" and not (self.answer or "").strip():
            raise ValueError("answer is required for clarification")
        return self


RejectionReasonCode = Literal[
    "too_rushed", "too_much_walking", "activity_mix_not_preferred",
    "schedule_too_late", "too_expensive", "other",
]


class RejectPlanRevisionRequest(BaseModel):
    reason_code: RejectionReasonCode | None = None
    reason_text: str | None = Field(default=None, max_length=2000)

    @field_validator("reason_text")
    @classmethod
    def normalize_reason_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class PlanningRunExecutionResponse(BaseModel):
    run: PlanningRunResponse
    pending_interrupt: PlanningPendingInterrupt | None = None


class DynamicReplanResponse(BaseModel):
    run: PlanningRunResponse
    trigger_event_id: uuid.UUID


TripExecutionStatus = Literal["not_started", "in_progress", "paused", "completed"]
ActivityExecutionStatus = Literal["pending", "arrived", "in_progress", "completed", "skipped"]
TripExecutionAction = Literal["arrive", "start_activity", "complete", "skip", "pause", "resume", "finish"]
DynamicReplanTrigger = Literal["delay", "weather_change", "fatigue", "budget_change", "user_change"]


class TripExecutionStart(BaseModel):
    day_plan_id: uuid.UUID | None = None


class TripExecutionActionRequest(BaseModel):
    action: TripExecutionAction
    activity_id: uuid.UUID | None = None
    delay_minutes: int | None = Field(default=None, ge=0, le=1440)


class ExtendStayRequest(BaseModel):
    client_action_id: uuid.UUID
    extension_minutes: int = Field(gt=0, le=480)
    reason: str | None = Field(default=None, max_length=500)
    # Optional during the Phase 1A rollout so older clients remain compatible.
    # When supplied it fences an experience command against a newer itinerary.
    expected_itinerary_version: int | None = Field(default=None, gt=0)


class ExtendStayResponse(BaseModel):
    activity_execution_id: uuid.UUID
    status: ActivityExecutionStatus
    extension_minutes: int
    total_extension_minutes: int
    projected_end_at: datetime | None = None
    replayed: bool = False
    replanning_status: str | None = None
    server_timestamp: datetime


class LeaveEarlyRequest(BaseModel):
    client_action_id: uuid.UUID
    reason: str | None = Field(default=None, max_length=500)
    expected_itinerary_version: int | None = Field(default=None, gt=0)


class LeaveEarlyResponse(BaseModel):
    activity_execution_id: uuid.UUID
    status: Literal["completed"]
    actual_started_at: datetime
    actual_ended_at: datetime
    actual_dwell_minutes: int
    replayed: bool = False
    server_timestamp: datetime



class DynamicReplanRequest(BaseModel):
    trigger: DynamicReplanTrigger
    details: str = Field(min_length=1, max_length=1000)


class ActivityExecutionResponse(BaseModel):
    id: uuid.UUID | None = None
    activity_id: uuid.UUID
    day_plan_id: uuid.UUID
    day_date: date
    name: str
    scheduled_time: time
    estimated_cost_fen: int
    status: ActivityExecutionStatus
    actual_arrived_at: datetime | None = None
    actual_started_at: datetime | None = None
    actual_ended_at: datetime | None = None
    delay_minutes: int = 0


class TravelEventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    activity_id: uuid.UUID | None = None
    occurred_at: datetime
    details: dict = Field(default_factory=dict)


class TripExecutionResponse(BaseModel):
    id: uuid.UUID | None = None
    trip_id: uuid.UUID
    status: TripExecutionStatus
    current_date: date
    current_day_plan_id: uuid.UUID | None = None
    current_activity_id: uuid.UUID | None = None
    actual_started_at: datetime | None = None
    actual_ended_at: datetime | None = None
    paused_at: datetime | None = None
    schedule_delay_minutes: int = 0
    remaining_activity_count: int = 0
    remaining_estimated_cost_fen: int = 0
    activities: list[ActivityExecutionResponse] = Field(default_factory=list)
    events: list[TravelEventResponse] = Field(default_factory=list)


NavigationSessionStatus = Literal[
    "created", "active", "rerouting", "arrived", "completed", "failed", "cancelled", "superseded"
]


class NavigationCoordinate(BaseModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)


class NavigationSessionCreate(BaseModel):
    trip_execution_id: uuid.UUID
    from_activity_id: uuid.UUID
    to_activity_id: uuid.UUID


class NavigationStartRequest(BaseModel):
    """Client expectation used to fence a start request against a new itinerary."""

    expected_itinerary_version: int | None = Field(default=None, gt=0)


class NavigationStartResponse(BaseModel):
    navigation_session: "NavigationSessionResponse"
    execution: TripExecutionResponse
    resumed: bool


class NavigationLocationUpdate(BaseModel):
    sequence: int = Field(gt=0)
    itinerary_version: int = Field(gt=0)
    location: NavigationCoordinate
    observed_at: datetime


NavigationObservationSource = Literal["simulation", "real_gps"]
NavigationRuntimeStatus = Literal["navigating", "rerouting", "paused", "arrived"]
NavigationRiskLevel = Literal["normal", "warning", "critical", "infeasible"]


class NavigationObservation(BaseModel):
    """Facts emitted by a navigation client; never a command to replan."""

    session_id: uuid.UUID
    itinerary_version: int = Field(gt=0)
    sequence: int = Field(gt=0)
    observed_at: datetime
    position: NavigationCoordinate
    coordinate_system: Literal["gcj02", "wgs84"]
    location_accuracy_meters: float = Field(ge=0, le=100_000)
    remaining_distance_meters: int = Field(ge=0)
    remaining_duration_seconds: int = Field(ge=0)
    eta: datetime
    route_revision: int = Field(ge=0)
    navigation_status: NavigationRuntimeStatus
    source: NavigationObservationSource

    @field_validator("observed_at", "eta")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value


class NavigationDisruptionReference(BaseModel):
    id: uuid.UUID
    event_type: Literal["missed_time_window", "itinerary_infeasible"]
    impacted_identity: str


class NavigationRecoveryPlanningReference(BaseModel):
    id: uuid.UUID
    status: PlanningRunStatus


class NavigationObservationResponse(BaseModel):
    session_id: uuid.UUID
    itinerary_version: int
    accepted_sequence: int
    replayed: bool = False
    session_status: NavigationSessionStatus
    current_eta: datetime
    remaining_distance_meters: int
    remaining_duration_seconds: int
    risk_level: NavigationRiskLevel
    minimum_downstream_slack_minutes: int | None = None
    first_impacted_activity_id: uuid.UUID | None = None
    active_disruption: NavigationDisruptionReference | None = None
    recovery_planning: NavigationRecoveryPlanningReference | None = None
    server_timestamp: datetime


class NavigationSessionActionRequest(BaseModel):
    action: Literal["complete", "cancel"]


class NavigationSessionResponse(BaseModel):
    id: uuid.UUID
    trip_id: uuid.UUID
    trip_execution_id: uuid.UUID
    from_activity_id: uuid.UUID
    to_activity_id: uuid.UUID
    formal_route_leg_id: uuid.UUID | None = None
    itinerary_version: int
    travel_mode: RouteMode
    coordinate_system: str
    origin: NavigationCoordinate
    destination: NavigationCoordinate
    planned_departure_at: datetime
    planned_arrival_at: datetime
    current_eta: datetime | None = None
    remaining_distance_meters: int | None = None
    current_duration_minutes: int | None = None
    progress_ratio: float | None = None
    provider: str | None = None
    provider_metadata: dict = Field(default_factory=dict)
    route_path: list[tuple[float, float]] = Field(default_factory=list)
    route_revision: int
    last_location_sequence: int
    last_location: NavigationCoordinate | None = None
    last_location_accuracy_meters: float | None = None
    last_location_at: datetime | None = None
    remaining_duration_seconds: int | None = None
    navigation_status: NavigationRuntimeStatus | None = None
    observation_source: NavigationObservationSource | None = None
    status: NavigationSessionStatus
    state_version: int
    created_at: datetime
    updated_at: datetime


class ActivityExperienceProgressResponse(BaseModel):
    """Derived experience timing for the current activity; no extra authority."""

    activity_execution_id: uuid.UUID
    activity_id: uuid.UUID
    planned_duration_minutes: int
    actual_started_at: datetime | None = None
    actual_ended_at: datetime | None = None
    elapsed_experience_minutes: int | None = None
    total_extension_minutes: int = 0
    projected_end_at: datetime | None = None


class ExperienceTimeImpactResponse(BaseModel):
    source: Literal["activity_experience"] = "activity_experience"
    time_shift_minutes: int | None = None
    impact_state: Literal["unavailable", "none", "absorbed", "at_risk", "infeasible"]
    minimum_downstream_slack_minutes: int | None = None
    first_impacted_activity_id: uuid.UUID | None = None
    fixed_window_feasible: bool | None = None
    day_end_feasible: bool | None = None
    downstream_schedule: list[dict] = Field(default_factory=list)


class RecoveryPlanningResponse(BaseModel):
    """Stable product read model; never exposes a PlanningRun trigger dump."""

    source: Literal["navigation_disruption", "activity_experience"]
    status: Literal["queued", "planning", "awaiting_confirmation", "accepted", "rejected", "superseded", "failed"]
    planning_run_id: uuid.UUID
    reason_summary: str
    trigger_activity_id: uuid.UUID | None = None
    trigger_activity_name: str | None = None
    time_shift_minutes: int | None = None
    minimum_downstream_slack_minutes: int | None = None
    first_impacted_activity_id: uuid.UUID | None = None
    pending_revision: dict | None = None
    source_detail: dict = Field(default_factory=dict)


class ExecutionReadModelResponse(BaseModel):
    """UI-facing projection of persisted execution facts, never a new authority."""
    trip_id: uuid.UUID
    itinerary_version: int
    execution: TripExecutionResponse
    navigation_session: NavigationSessionResponse | None = None
    current_activity_name: str | None = None
    current_activity_experience: ActivityExperienceProgressResponse | None = None
    experience_impact: ExperienceTimeImpactResponse | None = None
    navigation_target_name: str | None = None
    risk_level: Literal["normal", "eta_delayed", "disruption", "unknown"]
    minimum_downstream_slack_minutes: int | None = None
    first_impacted_activity_id: uuid.UUID | None = None
    active_disruption: dict | None = None
    # Latest attempt for the active disruption; it may be terminal (for
    # example rejected) while the disruption itself still remains active.
    active_recovery_run: dict | None = None
    recovery_revision: dict | None = None
    recovery_planning: RecoveryPlanningResponse | None = None
    generated_at: datetime


class CandidateActivity(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=80)
    day_date: date
    place_candidate_id: uuid.UUID
    planned_start_time: time
    duration_minutes: int = Field(gt=0, le=1440)
    estimated_cost_fen: int = Field(ge=0)
    transport_mode_to_here: PreferenceTransportMode
    reason: str = Field(default="", max_length=1000)
    source_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    replaces_activity_id: uuid.UUID | None = None
    locked: bool = False


class CandidateRouteLeg(BaseModel):
    day_date: date
    from_activity_ref: str = Field(min_length=1, max_length=80)
    to_activity_ref: str = Field(min_length=1, max_length=80)
    position: int = Field(ge=0)
    mode: PreferenceTransportMode
    distance_meters: int = Field(ge=0)
    duration_minutes: int = Field(ge=0)
    provider: str = Field(min_length=1, max_length=40)
    is_estimated: bool = False
    path: list[tuple[float, float]] = Field(default_factory=list)
    alternatives: list[RouteAlternativeResponse] = Field(default_factory=list)
    calculated_at: datetime


class DecisionEvidence(BaseModel):
    source_type: Literal["goal", "decision_context", "decision_memory", "activity_semantics", "route_fact", "execution_state", "provider_fact"]
    fact_key: Literal[
        "end_before", "max_walking_minutes", "pace", "minimize_walking", "preserve_existing",
        "walking_before_minutes", "walking_after_minutes", "route_before_minutes", "route_after_minutes",
        "importance", "can_skip", "minimum_duration_minutes", "source_revision_id", "rejection_reason_code",
        "place_candidate_id", "formal_itinerary", "protected_constraints", "route_context", "user_preferences",
        "current_activity_id", "delay_minutes", "minimum_downstream_slack_minutes", "route_schedule_adjusted",
    ]
    value: str | int | float | bool | None = None


class DecisionSemanticRef(BaseModel):
    activity_id: uuid.UUID
    importance: Literal["must_do", "high", "normal", "low"] | None = None
    can_skip: bool | None = None
    minimum_duration_minutes: int | None = None


class DecisionLedgerEntry(BaseModel):
    decision_id: str = Field(min_length=1, max_length=80)
    source: Literal["planner", "deterministic_route_repair"] = "planner"
    action_type: Literal["preserve", "remove", "add", "move", "shorten", "extend", "change_travel_mode"]
    target_activity_id: uuid.UUID | None = None
    target_place_candidate_id: uuid.UUID | None = None
    before: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)
    primary_reason: Literal[
        "satisfy_hard_goal", "improve_soft_goal", "respect_user_feedback", "preserve_must_do",
        "respect_minimum_duration", "preserve_locked_activity", "reduce_walking",
        "reduce_travel_time", "resolve_schedule_conflict", "reduce_day_density",
        "preserve_existing", "other",
    ]
    supporting_evidence: list[DecisionEvidence] = Field(default_factory=list)
    goal_refs: list[str] = Field(default_factory=list)
    memory_refs: list[uuid.UUID] = Field(default_factory=list)
    semantic_refs: list[DecisionSemanticRef] = Field(default_factory=list)
    tradeoff_cost: dict[str, int | bool] = Field(default_factory=dict)


class CandidatePlanSnapshot(BaseModel):
    explanation: str = Field(default="", max_length=2000)
    activities: list[CandidateActivity] = Field(max_length=100)
    route_legs: list[CandidateRouteLeg] = Field(default_factory=list, max_length=200)
    # None marks a historical/non-Planner snapshot; new Planner drafts always set a list.
    decision_ledger: list[DecisionLedgerEntry] | None = None
    # Sanitized parser findings about explanations/provenance, never model text.
    provenance_parse_errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_candidate_ids(self) -> "CandidatePlanSnapshot":
        ids = [item.candidate_id for item in self.activities]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate_id values must be unique")
        route_positions = [(leg.day_date, leg.position) for leg in self.route_legs]
        if len(route_positions) != len(set(route_positions)):
            raise ValueError("route leg positions must be unique within each day")
        return self


class PlanRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    planning_run_id: uuid.UUID
    trip_id: uuid.UUID
    revision_number: int
    reason: str
    before_snapshot: dict
    proposed_snapshot: CandidatePlanSnapshot
    difference_summary: dict
    validation_result: dict
    planning_goals: PlanningGoals | None = None
    goal_satisfaction: GoalSatisfactionResult | None = None
    source_ids: list[str]
    status: PlanRevisionStatus
    rejection_reason_code: RejectionReasonCode | None = None
    rejection_reason_text: str | None = None
    created_at: datetime
    decided_at: datetime | None


class PlanValidationIssue(BaseModel):
    code: str
    message: str
    candidate_id: str | None = None
    details: dict = Field(default_factory=dict)


class PlanValidationResult(BaseModel):
    valid: bool
    errors: list[PlanValidationIssue] = Field(default_factory=list)
    warnings: list[PlanValidationIssue] = Field(default_factory=list)


class DemoResetResponse(BaseModel):
    trip_id: uuid.UUID
    status: Literal["seeded", "reset"]
