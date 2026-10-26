"""Canonical read-through, owned repeatable-read/read-only DB transaction."""
import uuid
from datetime import UTC, datetime

from .interfaces import ProviderUnavailable
from .models import FactBundle, FactRequirement, FactType, GeoPoint, LocationValue, MeasurementValue, StatusValue, TimestampValue
from .normalization import evidence_record, fact_record
from .policies import FactFreshnessPolicy


class ExecutionFactAdapter:
    name, read_through = "roamsync_execution", True
    def __init__(self, freshness: FactFreshnessPolicy, *, reader=None, allow_simulation: bool = False):
        self.freshness, self.reader, self.allow_simulation = freshness, reader or SqlExecutionReader(), allow_simulation

    def supports(self, requirement):
        return requirement.fact_type in {FactType.ACTIVITY_STATUS, FactType.ACTUAL_START, FactType.ACTUAL_END,
                                         FactType.NAV_POSITION, FactType.NAV_ETA, FactType.NAV_REMAINING_DISTANCE}

    async def fetch(self, requirement: FactRequirement, *, now: datetime) -> FactBundle:
        snapshot = await self.reader.read(requirement)
        if snapshot is None:
            return FactBundle()
        kind = requirement.fact_type
        canonical_time = None
        if requirement.subject.kind == "navigation_session":
            if (snapshot["status"] not in {"active", "rerouting"} or snapshot["execution_status"] != "in_progress"
                or snapshot["observation_source"] not in ({"real_gps", "simulation"} if self.allow_simulation else {"real_gps"})
                or not snapshot["last_observation_fingerprint"] or snapshot["last_location_sequence"] < 1
                or snapshot["last_location_at"] is None or snapshot["navigation_status"] not in {"navigating", "rerouting"}):
                return FactBundle()  # Planned/initial route estimates aren't current observations.
            canonical_time = snapshot["last_location_at"]
            if kind == FactType.NAV_ETA:
                if snapshot["current_eta"] is None:
                    return FactBundle()
                value = TimestampValue(timestamp=snapshot["current_eta"])
            elif kind == FactType.NAV_REMAINING_DISTANCE:
                if snapshot["remaining_distance_meters"] is None:
                    return FactBundle()
                value = MeasurementValue(amount=snapshot["remaining_distance_meters"], unit="meters")
            else:
                if snapshot["longitude"] is None or snapshot["latitude"] is None:
                    return FactBundle()
                value = LocationValue(point=GeoPoint(longitude=snapshot["longitude"], latitude=snapshot["latitude"],
                    coordinate_system=snapshot["coordinate_system"]), accuracy_meters=snapshot["accuracy_meters"])
        elif kind == FactType.ACTIVITY_STATUS:
            value = StatusValue(status=snapshot["status"])
        else:
            stamp = snapshot["actual_started_at"] if kind == FactType.ACTUAL_START else snapshot["actual_ended_at"]
            if stamp is None:
                return FactBundle()
            value = TimestampValue(timestamp=stamp)
        # Actual start/end are historical values. Reading current DB state
        # confirms the record now; their event time is not the cache age.
        retrieved = snapshot["read_at"]
        metadata = {"itinerary_version":requirement.subject.itinerary_version,
                    "row_updated_at":snapshot["updated_at"].isoformat()}
        if canonical_time is not None:
            metadata.update(route_revision=requirement.subject.route_revision,
                            accepted_sequence=snapshot["last_location_sequence"], observation_source=snapshot["observation_source"])
        evidence = evidence_record(provider="roamsync", source_type="canonical_execution",
            source_reference="canonical:"+requirement.subject.kind+":"+requirement.subject.ref, retrieved_at=retrieved,
            provider_observed_at=canonical_time, authority_level="authoritative",
            normalized_snapshot={"fact_type":kind.value, "value":value.model_dump(mode="json")}, metadata=metadata)
        fact = fact_record(fact_type=kind, subject=requirement.subject, value=value, evidence=evidence, freshness=self.freshness,
            nature="canonical_prediction" if kind == FactType.NAV_ETA else "canonical_record")
        return FactBundle(facts=(fact,), evidence=(evidence,))


class SqlExecutionReader:
    def __init__(self, session_factory=None):
        self.session_factory = session_factory

    async def read(self, requirement: FactRequirement) -> dict | None:
        from sqlalchemy import select, text
        from app.database import ActivityExecution, NavigationSession, Trip, TripExecution, session_factory
        subject = requirement.subject
        async with (self.session_factory or session_factory)() as session:
            session.autoflush = False
            # Own session avoids flushing a caller's pending business mutations.
            await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            trip = await session.get(Trip, uuid.UUID(subject.trip_ref))
            execution = await session.get(TripExecution, uuid.UUID(subject.trip_execution_ref))
            if trip is None or execution is None or execution.trip_id != trip.id:
                return None
            if trip.version != subject.itinerary_version or execution.itinerary_version != subject.itinerary_version:
                raise ProviderUnavailable("canonical_version_mismatch")
            if subject.kind == "navigation_session":
                item = await session.get(NavigationSession, uuid.UUID(subject.ref))
                if item is None or item.trip_id != trip.id or item.trip_execution_id != execution.id:
                    return None
                if item.itinerary_version != subject.itinerary_version or item.route_revision != subject.route_revision:
                    raise ProviderUnavailable("canonical_version_mismatch")
                result = dict(status=item.status, execution_status=execution.status, current_eta=item.current_eta,
                    remaining_distance_meters=item.remaining_distance_meters, longitude=item.last_location_longitude,
                    latitude=item.last_location_latitude, coordinate_system=item.coordinate_system,
                    accuracy_meters=item.last_location_accuracy_meters, last_location_at=item.last_location_at,
                    last_location_sequence=item.last_location_sequence, last_observation_fingerprint=item.last_observation_fingerprint,
                    observation_source=item.observation_source, navigation_status=item.navigation_status, updated_at=item.updated_at)
            else:
                item = await session.scalar(select(ActivityExecution).where(ActivityExecution.id == uuid.UUID(subject.ref),
                    ActivityExecution.trip_execution_id == execution.id))
                if item is None:
                    return None
                result = dict(status=item.status, actual_started_at=item.actual_started_at, actual_ended_at=item.actual_ended_at,
                              updated_at=item.updated_at)
            result["read_at"] = datetime.now(UTC)
            return result  # Session exit rolls back; there is no flush/add/commit path.
