"""Provider-independent, bounded, versioned fact contracts (not reasoning)."""
import json
from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True, allow_inf_nan=False)


class FactType(str, Enum):
    PLACE_IDENTITY = "place.identity"
    PLACE_LOCATION = "place.location"
    PLACE_CATEGORY = "place.category"
    OPENING_HOURS = "place.opening_hours"
    OPERATIONAL_STATUS = "place.operational_status"
    TICKET_AVAILABILITY = "place.ticket_availability"
    WEATHER_CURRENT = "weather.current"
    WEATHER_FORECAST = "weather.forecast"
    ROUTE_DISTANCE = "route.distance"
    ROUTE_DURATION = "route.duration"
    ROUTE_ETA = "route.eta"
    ACTIVITY_STATUS = "execution.activity_status"
    ACTUAL_START = "execution.actual_start"
    ACTUAL_END = "execution.actual_end"
    NAV_POSITION = "navigation.position"
    NAV_ETA = "navigation.eta"
    NAV_REMAINING_DISTANCE = "navigation.remaining_distance"


class AuthorityLevel(str, Enum):
    UNVERIFIED = "unverified"
    SECONDARY = "secondary"
    SPECIALIST = "specialist"
    AUTHORITATIVE = "authoritative"


class GeoPoint(Contract):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    coordinate_system: Literal["gcj02", "wgs84"]


class PlaceSubject(Contract):
    kind: Literal["place"] = "place"
    ref: str = Field(min_length=1, max_length=240)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    destination: str | None = Field(default=None, min_length=1, max_length=120)


class DestinationSubject(Contract):
    kind: Literal["destination"] = "destination"
    ref: str = Field(min_length=1, max_length=240)
    location: GeoPoint


class RouteSubject(Contract):
    kind: Literal["route"] = "route"
    ref: str = Field(min_length=1, max_length=240)
    origin: GeoPoint
    destination: GeoPoint
    travel_mode: Literal["walk", "transit", "driving"]
    destination_city: str = Field(default="", max_length=120)


class ExecutionSubject(Contract):
    kind: Literal["activity_execution", "navigation_session"]
    ref: str = Field(min_length=1, max_length=240)
    trip_ref: str = Field(min_length=1, max_length=240)
    trip_execution_ref: str = Field(min_length=1, max_length=240)
    itinerary_version: int = Field(gt=0)
    route_revision: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def navigation_revision(self):
        if self.kind == "navigation_session" and self.route_revision is None:
            raise ValueError("navigation subject requires route_revision")
        return self


FactSubject = Annotated[PlaceSubject | DestinationSubject | RouteSubject | ExecutionSubject, Field(discriminator="kind")]


class FactScope(Contract):
    kind: Literal["global", "destination", "place", "trip_execution", "navigation_session"]
    ref: str = Field(min_length=1, max_length=240)


def scope_for(subject) -> FactScope:
    if isinstance(subject, ExecutionSubject):
        kind = "navigation_session" if subject.kind == "navigation_session" else "trip_execution"
        return FactScope(kind=kind, ref=subject.ref if kind == "navigation_session" else subject.trip_execution_ref)
    if subject.kind == "route":
        return FactScope(kind="global", ref="global")
    return FactScope(kind="destination" if subject.kind == "destination" else "place", ref=subject.ref)


class IdentityValue(Contract):
    kind: Literal["identity"] = "identity"
    provider_place_id: str = Field(min_length=1, max_length=240)
    name: str = Field(min_length=1, max_length=240)


class LocationValue(Contract):
    kind: Literal["location"] = "location"
    point: GeoPoint
    accuracy_meters: float | None = Field(default=None, ge=0)


class CategoryValue(Contract):
    kind: Literal["category"] = "category"
    category: str = Field(min_length=1, max_length=240)


class MeasurementValue(Contract):
    kind: Literal["measurement"] = "measurement"
    amount: float = Field(ge=0)
    unit: Literal["meters", "minutes"]


class TimestampValue(Contract):
    kind: Literal["timestamp"] = "timestamp"
    timestamp: AwareDatetime


class StatusValue(Contract):
    kind: Literal["status"] = "status"
    status: Literal["open", "closed", "unknown", "pending", "arrived", "in_progress", "completed", "skipped", "available", "sold_out"]


class OpeningHoursValue(Contract):
    kind: Literal["opening_hours"] = "opening_hours"
    opens_at: AwareDatetime
    closes_at: AwareDatetime

    @model_validator(mode="after")
    def ordered(self):
        if self.closes_at <= self.opens_at:
            raise ValueError("closing time must follow opening time")
        return self


class WeatherValue(Contract):
    kind: Literal["weather"] = "weather"
    temperature_celsius: float = Field(ge=-100, le=70)
    precipitation_probability_percent: float = Field(ge=0, le=100)
    weather_code: int = Field(ge=0, le=99)


FactValue = Annotated[IdentityValue | LocationValue | CategoryValue | MeasurementValue | TimestampValue |
                      StatusValue | OpeningHoursValue | WeatherValue, Field(discriminator="kind")]

_VALUE_KINDS = {
    FactType.PLACE_IDENTITY:"identity", FactType.PLACE_LOCATION:"location", FactType.PLACE_CATEGORY:"category",
    FactType.OPENING_HOURS:"opening_hours", FactType.OPERATIONAL_STATUS:"status", FactType.TICKET_AVAILABILITY:"status",
    FactType.WEATHER_CURRENT:"weather", FactType.WEATHER_FORECAST:"weather", FactType.ROUTE_DISTANCE:"measurement",
    FactType.ROUTE_DURATION:"measurement", FactType.ROUTE_ETA:"timestamp", FactType.ACTIVITY_STATUS:"status",
    FactType.ACTUAL_START:"timestamp", FactType.ACTUAL_END:"timestamp", FactType.NAV_POSITION:"location",
    FactType.NAV_ETA:"timestamp", FactType.NAV_REMAINING_DISTANCE:"measurement",
}


def validate_subject(fact_type: FactType, subject):
    expected = ("place" if fact_type.value.startswith("place.") else "destination" if fact_type.value.startswith("weather.")
                else "route" if fact_type.value.startswith("route.") else "activity_execution" if fact_type.value.startswith("execution.")
                else "navigation_session")
    if subject.kind != expected:
        raise ValueError("fact type and subject kind disagree")


class TimeScope(Contract):
    start: AwareDatetime
    end: AwareDatetime | None = None

    @model_validator(mode="after")
    def ordered(self):
        if self.end is not None and self.end <= self.start:
            raise ValueError("time range must be non-empty; end is exclusive")
        return self


class EvidenceRecord(Contract):
    id: str = Field(min_length=1, max_length=240)
    provider: str = Field(min_length=1, max_length=80)
    source_type: Literal["structured_api", "official_notice", "official_schedule", "canonical_execution", "search_candidate"]
    source_reference: str = Field(min_length=1, max_length=2000)
    retrieved_at: AwareDatetime
    provider_observed_at: AwareDatetime | None = None
    authority_level: AuthorityLevel
    raw_snapshot_ref: str | None = Field(default=None, pattern=r"^sha256:[a-f0-9]{64}$")
    normalized_snapshot: dict[str, JsonValue]
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    payload_trust: Literal["untrusted_data_no_tool_authority"] = "untrusted_data_no_tool_authority"

    @model_validator(mode="after")
    def bounded(self):
        if self.provider_observed_at is not None and self.provider_observed_at > self.retrieved_at:
            raise ValueError("provider observation cannot be later than retrieval")
        if len(json.dumps(self.normalized_snapshot, ensure_ascii=False, allow_nan=False).encode()) > 8192:
            raise ValueError("normalized evidence snapshot exceeds 8 KiB")
        if len(json.dumps(self.metadata, ensure_ascii=False, allow_nan=False).encode()) > 4096:
            raise ValueError("evidence metadata exceeds 4 KiB")
        return self


class TravelFact(Contract):
    id: str = Field(min_length=1, max_length=240)
    fact_type: FactType
    subject: FactSubject
    scope: FactScope
    value: FactValue
    nature: Literal["provider_assertion", "provider_prediction", "canonical_record", "canonical_prediction"]
    observed_at: AwareDatetime
    effective_from: AwareDatetime | None = None
    effective_until: AwareDatetime | None = None
    fresh_until: AwareDatetime
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=16)
    specificity: Literal["general", "time_specific"] = "general"

    @model_validator(mode="after")
    def consistent(self):
        validate_subject(self.fact_type, self.subject)
        if self.scope != scope_for(self.subject):
            raise ValueError("fact scope does not match subject")
        if self.value.kind != _VALUE_KINDS[self.fact_type]:
            raise ValueError("fact value kind does not match fact type")
        if self.fresh_until < self.observed_at:
            raise ValueError("fresh_until cannot precede observation")
        if self.effective_from and self.effective_until and self.effective_until <= self.effective_from:
            raise ValueError("effective interval must be non-empty")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("duplicate evidence references")
        if self.specificity == "time_specific" and (self.effective_from is None or self.effective_until is None):
            raise ValueError("time-specific assertions require a bounded effective interval")
        expected_unit = "minutes" if self.fact_type == FactType.ROUTE_DURATION else "meters"
        if isinstance(self.value, MeasurementValue) and self.value.unit != expected_unit:
            raise ValueError("measurement unit does not match fact type")
        if self.fact_type == FactType.OPERATIONAL_STATUS and self.value.status not in {"open", "closed", "unknown"}:
            raise ValueError("invalid operational status")
        if self.fact_type == FactType.ACTIVITY_STATUS and self.value.status not in {"pending", "arrived", "in_progress", "completed", "skipped"}:
            raise ValueError("invalid activity execution status")
        if self.fact_type == FactType.TICKET_AVAILABILITY and self.value.status not in {"available", "sold_out", "unknown"}:
            raise ValueError("invalid ticket availability")
        if self.fact_type == FactType.WEATHER_FORECAST and self.nature != "provider_prediction":
            raise ValueError("forecast must be marked as provider_prediction")
        if self.fact_type == FactType.ROUTE_DURATION and self.nature != "provider_prediction":
            raise ValueError("route duration is a provider prediction, not measured arrival")
        if self.fact_type == FactType.NAV_ETA and self.nature != "canonical_prediction":
            raise ValueError("navigation ETA is a canonical prediction")
        canonical = self.fact_type.value.startswith(("execution.", "navigation."))
        if canonical != self.nature.startswith("canonical_"):
            raise ValueError("canonical and external fact origins must remain distinct")
        if self.fact_type == FactType.ROUTE_ETA and self.nature != "provider_prediction":
            raise ValueError("route ETA is a provider prediction")
        return self


class FactRequirement(Contract):
    contract_version: Literal["travel-facts-v1"] = "travel-facts-v1"
    fact_type: FactType
    subject: FactSubject
    time_scope: TimeScope | None = None  # None means current, never an implied future date.
    required_freshness_seconds: int | None = Field(default=None, ge=0)
    minimum_authority: AuthorityLevel = AuthorityLevel.SPECIALIST
    required: bool = True
    reason: str = Field(default="", max_length=240)
    allow_stale: bool = False

    @model_validator(mode="after")
    def consistent(self):
        validate_subject(self.fact_type, self.subject)
        return self


class FactBundle(Contract):
    facts: tuple[TravelFact, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()

    @model_validator(mode="after")
    def references(self):
        indexed = {record.id:record for record in self.evidence}
        if len(indexed) != len(self.evidence) or len({fact.id for fact in self.facts}) != len(self.facts):
            raise ValueError("duplicate identities in bundle")
        for fact in self.facts:
            for ref in fact.evidence_refs:
                if ref not in indexed:
                    raise ValueError("fact has dangling evidence reference")
                if fact.observed_at > indexed[ref].retrieved_at:
                    raise ValueError("fact observation exceeds evidence retrieval")
        return self


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    FUTURE_EFFECTIVE = "future_effective"
    EXPIRED = "expired"
    NO_EVIDENCE = "no_evidence"


class RejectedCandidate(Contract):
    fact: TravelFact
    freshness_status: FreshnessStatus
    reason: str


class ResolvedFact(Contract):
    contract_version: Literal["travel-facts-v1"] = "travel-facts-v1"
    requirement: FactRequirement
    resolution_status: Literal["resolved", "conflicting", "stale", "unavailable", "unsupported", "no_evidence"]
    freshness_status: FreshnessStatus = FreshnessStatus.NO_EVIDENCE
    value: FactValue | None = None
    selected_fact: TravelFact | None = None
    selected_evidence: tuple[EvidenceRecord, ...] = ()
    conflicting_facts: tuple[TravelFact, ...] = ()
    conflicting_evidence: tuple[EvidenceRecord, ...] = ()
    rejected_candidates: tuple[RejectedCandidate, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    confidence: Literal["policy_supported", "corroborated", "limited", "none"] = "none"
    usable_as_current: bool = False
    provider_failures: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    resolved_at: AwareDatetime

    @model_validator(mode="after")
    def safe_result(self):
        if self.usable_as_current and (self.resolution_status != "resolved" or self.freshness_status != FreshnessStatus.FRESH):
            raise ValueError("only resolved fresh facts are usable as current")
        if self.value is not None and (self.selected_fact is None or self.selected_fact.value != self.value):
            raise ValueError("value must belong to selected fact")
        if self.resolution_status == "conflicting" and self.value is not None:
            raise ValueError("unresolved conflicts must not publish a value")
        if self.resolution_status in {"unavailable", "unsupported", "no_evidence"} and self.value is not None:
            raise ValueError("evidence gaps must not publish a value")
        if self.resolution_status == "resolved" and (self.value is None or not self.selected_evidence):
            raise ValueError("resolved facts require a value and selected evidence")
        refs = {record.id for record in self.evidence}
        if len(refs) != len(self.evidence):
            raise ValueError("duplicate result evidence")
        if any(record.id not in refs for record in self.selected_evidence + self.conflicting_evidence):
            raise ValueError("resolution evidence must be preserved")
        facts = self.conflicting_facts + tuple(item.fact for item in self.rejected_candidates)
        if self.selected_fact is not None:
            facts += (self.selected_fact,)
        for fact in facts:
            if fact.fact_type != self.requirement.fact_type or fact.subject != self.requirement.subject:
                raise ValueError("result contains unrelated fact")
            if any(ref not in refs for ref in fact.evidence_refs):
                raise ValueError("result has dangling fact evidence")
        return self
