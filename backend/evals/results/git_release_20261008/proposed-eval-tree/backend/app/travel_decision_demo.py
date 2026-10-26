"""Create or reset the isolated Travel Decision Agent demo trip."""
import argparse
import asyncio

from sqlalchemy import func, select

from app.database import (
    Activity,
    AssistantSession,
    DayPlan,
    PlanningRun,
    PlanRevision,
    RouteLeg,
    Trip,
    TripExecution,
    TripPreferences,
    session_factory,
)
from app.demo_seed import TRAVEL_DECISION_DEMO_TRIP_ID, seed_travel_decision_demo_data


async def validate_reset() -> dict[str, int]:
    """Fail closed unless the dedicated trip is back at its rehearsable baseline."""
    async with session_factory() as session:
        trip = await session.get(Trip, TRAVEL_DECISION_DEMO_TRIP_ID)
        if trip is None:
            raise RuntimeError("reset validation: demo Trip is missing")
        day = (await session.scalars(select(DayPlan).where(DayPlan.trip_id == trip.id))).one()
        activities = list((await session.scalars(
            select(Activity).where(Activity.day_plan_id == day.id).order_by(Activity.position)
        )).all())
        routes = list((await session.scalars(
            select(RouteLeg).where(RouteLeg.day_plan_id == day.id)
        )).all())
        preferences = await session.get(TripPreferences, trip.id)
        expected = {
            "trip_version": 1,
            "activity_count": 5,
            "route_leg_count": 4,
            "pending_revisions": 0,
            "rejected_demo_revisions": 0,
            "decision_memory_count": 0,
            "assistant_sessions": 0,
            "executions": 0,
        }
        pending = await session.scalar(select(func.count()).select_from(PlanRevision).where(
            PlanRevision.trip_id == trip.id, PlanRevision.status == "pending"
        ))
        rejected = await session.scalar(select(func.count()).select_from(PlanRevision).where(
            PlanRevision.trip_id == trip.id, PlanRevision.status == "rejected"
        ))
        run_count = await session.scalar(select(func.count()).select_from(PlanningRun).where(
            PlanningRun.trip_id == trip.id
        ))
        assistant_count = await session.scalar(select(func.count()).select_from(AssistantSession).where(
            AssistantSession.trip_id == trip.id
        ))
        execution_count = await session.scalar(select(func.count()).select_from(TripExecution).where(
            TripExecution.trip_id == trip.id
        ))
        actual = {
            "trip_version": trip.version,
            "activity_count": len(activities),
            "route_leg_count": len(routes),
            "pending_revisions": int(pending or 0),
            "rejected_demo_revisions": int(rejected or 0),
            # Demo Memory is derived only from rejected revisions.
            "decision_memory_count": int(rejected or 0),
            "assistant_sessions": int(assistant_count or 0),
            "executions": int(execution_count or 0),
        }
        mismatches = [f"{key} expected {value}, got {actual[key]}" for key, value in expected.items() if actual[key] != value]
        if trip.start_date.isoformat() != "2026-10-20" or day.date.isoformat() != "2026-10-20":
            mismatches.append("demo target day is not 2026-10-20")
        if [a.importance for a in activities] != ["high", "must_do", "normal", "normal", "low"]:
            mismatches.append("activity importance baseline differs")
        if activities[1].can_skip is not False or activities[1].minimum_duration_minutes != 60:
            mismatches.append("China Academy of Art must_do semantics differ")
        if len(routes) != 4 or any(not route.provider or not route.duration_minutes or not route.distance_meters for route in routes):
            mismatches.append("formal route facts are incomplete")
        if preferences is None:
            mismatches.append("trip preferences are missing")
        if mismatches:
            raise RuntimeError("reset validation failed: " + "; ".join(mismatches))
        return actual


async def run(reset: bool) -> None:
    async with session_factory() as session:
        changed = await seed_travel_decision_demo_data(session, reset=reset)
    action = "reset" if reset else "seeded" if changed else "already exists"
    print(f"Travel Decision Agent demo trip {TRAVEL_DECISION_DEMO_TRIP_ID}: {action}")
    if reset:
        baseline = await validate_reset()
        print("RESET VALIDATION PASS: " + ", ".join(f"{key}={value}" for key, value in baseline.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the isolated Travel Decision Agent demo trip.")
    parser.add_argument("--reset", action="store_true", help="Reset only this demo trip and dependent planning data.")
    args = parser.parse_args()
    asyncio.run(run(args.reset))


if __name__ == "__main__":
    main()
