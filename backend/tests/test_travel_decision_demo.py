import asyncio

from sqlalchemy import select

from app.database import Activity, DayPlan, PlanningRun, PlanRevision, RouteLeg, Trip, session_factory
from app.demo_seed import TRAVEL_DECISION_DEMO_TRIP_ID, seed_travel_decision_demo_data


def test_dedicated_demo_seed_and_reset_preserve_semantics_and_clear_decisions():
    async def exercise():
        async with session_factory() as session:
            await seed_travel_decision_demo_data(session, reset=True)
        async with session_factory() as session:
            trip = await session.get(Trip, TRAVEL_DECISION_DEMO_TRIP_ID)
            assert trip is not None
            assert trip.destination_adcode == "330100"
            assert trip.destination_citycode == "0571"
            day = (await session.scalars(select(DayPlan).where(DayPlan.trip_id == trip.id))).one()
            activities = (await session.scalars(select(Activity).where(Activity.day_plan_id == day.id).order_by(Activity.position))).all()
            routes = (await session.scalars(select(RouteLeg).where(RouteLeg.day_plan_id == day.id))).all()
            assert len(activities) == 5
            assert len(routes) == 4
            assert all(not route.is_estimated or route.provider == "RoamSync Estimate" for route in routes)
            assert [activity.importance for activity in activities] == ["high", "must_do", "normal", "normal", "low"]
            assert activities[1].can_skip is False
            assert activities[1].minimum_duration_minutes == 60
            assert all(activity.schedule_locked is False for activity in activities)
            run = PlanningRun(trip_id=trip.id, run_type="replan", status="rejected", user_request="test", base_trip_version=trip.version)
            session.add(run)
            await session.flush()
            session.add(PlanRevision(
                planning_run_id=run.id, trip_id=trip.id, revision_number=1, reason="test",
                before_snapshot={}, proposed_snapshot={}, difference_summary={}, validation_result={},
                source_ids=[], status="rejected", rejection_reason_code="too_rushed", rejection_reason_text="test",
            ))
            await session.commit()
        async with session_factory() as session:
            await seed_travel_decision_demo_data(session, reset=True)
        async with session_factory() as session:
            assert (await session.scalars(select(PlanningRun).where(PlanningRun.trip_id == TRAVEL_DECISION_DEMO_TRIP_ID))).all() == []
            assert (await session.scalars(select(PlanRevision).where(PlanRevision.trip_id == TRAVEL_DECISION_DEMO_TRIP_ID))).all() == []

    asyncio.run(exercise())
