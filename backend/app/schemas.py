import uuid
from datetime import date, datetime, time
from typing import Literal
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
    total_budget_fen: int = Field(gt=0)
    daily_budget_fen: int = Field(gt=0)
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
        if self.daily_budget_fen > self.total_budget_fen:
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
    total_budget_fen: int
    daily_budget_fen: int
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
    total_budget_fen: int
    total_spent_fen: int
    total_remaining_fen: int
    daily_budget_fen: int
    today_spent_fen: int
    today_remaining_fen: int
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

    @model_validator(mode="after")
    def require_exactly_one_place(self) -> "ActivityCreate":
        if (self.place_id is None) == (self.place_snapshot is None):
            raise ValueError("provide exactly one of place_id or place_snapshot")
        return self


class ActivityUpdate(BaseModel):
    version: int = Field(gt=0)
    custom_name: str | None = Field(default=None, max_length=160)
    scheduled_time: time | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
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
    remaining_fen: int
    ratio: float
    status: Literal["comfortable", "watch", "over"]


class PlanningBudgetResponse(BaseModel):
    trip_id: uuid.UUID
    total_planned_fen: int
    total_remaining_fen: int
    days: list[PlanningBudgetDayResponse]


class PlanningContextResponse(BaseModel):
    trip: TripResponse
    preferences: TripPreferencesResponse
    days: list[DayPlanResponse]
    candidates: list[PlaceCandidateResponse]
    actual_budget: BudgetResponse
    planning_budget: PlanningBudgetResponse
    generated_at: datetime


PlanningRunType = Literal["initial_plan", "replan"]
PlanningRunStatus = Literal[
    "queued", "researching", "awaiting_clarification", "planning", "validating", "awaiting_confirmation",
    "accepted", "rejected", "failed", "cancelled"
]
PlanRevisionStatus = Literal["pending", "accepted", "rejected", "superseded"]


class PlanningRunCreate(BaseModel):
    run_type: PlanningRunType = "initial_plan"
    user_request: str = Field(default="", max_length=4000)

    @field_validator("user_request")
    @classmethod
    def normalize_request(cls, value: str) -> str:
        return value.strip()


class PlanningRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trip_id: uuid.UUID
    run_type: PlanningRunType
    status: PlanningRunStatus
    user_request: str
    base_trip_version: int
    model_provider: str | None
    model_name: str | None
    token_usage: int
    error_code: str | None
    error_message: str | None
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


class PlanningRunExecutionResponse(BaseModel):
    run: PlanningRunResponse
    pending_interrupt: dict | None = None


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


class CandidatePlanSnapshot(BaseModel):
    activities: list[CandidateActivity] = Field(max_length=100)
    route_legs: list[CandidateRouteLeg] = Field(default_factory=list, max_length=200)

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
    source_ids: list[str]
    status: PlanRevisionStatus
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
