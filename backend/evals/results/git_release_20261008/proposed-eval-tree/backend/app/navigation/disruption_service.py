"""Persistence, deduplication and lifecycle for confirmed deterministic facts."""
from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import NavigationSession, TripDisruptionEvent
from app.navigation.event_detector import DetectedExecutionEvent


class DisruptionConflictError(Exception):
    pass


def disruption_dedup_key(session: NavigationSession, event: DetectedExecutionEvent) -> str:
    identity = event.impacted_identity or "trip"
    return f"{session.trip_execution_id}:{session.itinerary_version}:{event.event_type}:{identity}"


async def record_disruption(
    session: AsyncSession,
    navigation_session_id: uuid.UUID,
    event: DetectedExecutionEvent,
    *,
    commit: bool = True,
) -> TripDisruptionEvent | None:
    """Upsert one continuing macro disruption; observations never reach this layer."""
    if event.kind != "disruption":
        return None
    navigation = await session.get(NavigationSession, navigation_session_id)
    if navigation is None:
        raise DisruptionConflictError("navigation session not found")
    key = disruption_dedup_key(navigation, event)
    existing = await session.scalar(select(TripDisruptionEvent).where(TripDisruptionEvent.dedup_key == key, TripDisruptionEvent.status == "active").with_for_update())
    if existing is not None:
        existing.last_seen_at = event.occurred_at
        existing.impact_snapshot = event.impact_snapshot
        if commit:
            await session.commit()
        else:
            await session.flush()
        return existing
    created = TripDisruptionEvent(
        trip_id=navigation.trip_id, trip_execution_id=navigation.trip_execution_id,
        navigation_session_id=navigation.id, itinerary_version=navigation.itinerary_version,
        event_type=event.event_type, impacted_identity=event.impacted_identity or "trip",
        detected_at=event.occurred_at, last_seen_at=event.occurred_at,
        impact_snapshot=event.impact_snapshot, dedup_key=key,
    )
    session.add(created)
    if not commit:
        # Observation ingestion holds the NavigationSession row lock, so two
        # workers cannot reach this insert concurrently for the same live leg.
        # The database partial unique index remains the final dedup boundary.
        await session.flush()
        return created
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # A concurrent transaction won the partial unique-index race. Re-read
        # and treat the same business fact as an update, not another event.
        existing = await session.scalar(select(TripDisruptionEvent).where(TripDisruptionEvent.dedup_key == key, TripDisruptionEvent.status == "active").with_for_update())
        if existing is None:
            raise
        existing.last_seen_at = event.occurred_at
        existing.impact_snapshot = event.impact_snapshot
        await session.commit()
        return existing
    await session.refresh(created)
    return created
