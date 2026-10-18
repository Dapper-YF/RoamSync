"""Read persisted model notes, without conferring validated decision authority."""
import re

from pydantic import ValidationError
from sqlalchemy import select

from app.database import PlaceCandidate, PlanningRun, PlanRevision, Trip
from app.schemas import CandidatePlanSnapshot


async def read_saved_plan_notes(session, trip_id, message):
    formal_only = bool(re.search(r"正式|已接受|已保存|已应用", message))
    candidate_only = bool(re.search(r"候选|待确认|新方案", message))
    if formal_only and candidate_only:
        return None
    # Read at most two qualifying rows: ambiguity is never resolved by newest.
    for status in (["accepted"] if formal_only else ["pending"] if candidate_only else ["pending", "accepted"]):
        run_status = "awaiting_confirmation" if status == "pending" else "accepted"
        version = Trip.version if status == "pending" else Trip.version - 1
        query = (select(PlanRevision.id, PlanRevision.proposed_snapshot, PlanRevision.validation_result,
                        PlanningRun.id.label("run_id"), Trip.version.label("trip_version"))
                 .join(PlanningRun, PlanningRun.id == PlanRevision.planning_run_id)
                 .join(Trip, Trip.id == PlanRevision.trip_id)
                 .where(Trip.id == trip_id, PlanningRun.trip_id == trip_id,
                        PlanRevision.status == status, PlanningRun.status == run_status,
                        PlanningRun.base_trip_version == version).limit(2))
        rows = (await session.execute(query, execution_options={"autoflush": False})).all()
        if len(rows) > 1:
            return None
        if not rows:
            continue
        row = rows[0]
        if not isinstance(row.validation_result, dict) or row.validation_result.get("valid") is not True:
            return None
        try:
            snapshot = CandidatePlanSnapshot.model_validate(row.proposed_snapshot)
        except (ValidationError, TypeError):
            return None
        places = (await session.execute(select(PlaceCandidate.id, PlaceCandidate.name)
            .where(PlaceCandidate.trip_id == trip_id,
                   PlaceCandidate.id.in_([a.place_candidate_id for a in snapshot.activities])),
            execution_options={"autoflush": False})).all()
        names = {str(p.id): p.name for p in places}
        if any(str(a.place_candidate_id) not in names for a in snapshot.activities):
            return None
        mentioned = {str(p.id) for p in places if p.name in message}
        explicit_subject = re.search(r"(?:把|将)(.{1,40}?)(?:安排|放|排)", message)
        if explicit_subject and not mentioned:
            return None
        if len(mentioned) > 1:
            return None
        activities = [a for a in snapshot.activities if not mentioned or str(a.place_candidate_id) in mentioned]
        if mentioned and len(activities) != 1:
            return None
        # An explicit timing question must match the saved schedule, not merely
        # a venue name; mismatched times cannot inherit another decision's notes.
        requested_time = re.search(r"(\d{1,2})(?:点|时|[:：](\d{2}))", message)
        if requested_time and (len(activities) != 1 or
            activities[0].planned_start_time.strftime("%H:%M") != f"{int(requested_time[1]):02d}:{int(requested_time[2] or 0):02d}"):
            return None
        reasons = [] if mentioned else [snapshot.explanation.strip()[:1000]] if snapshot.explanation.strip() else []
        for activity in activities[:10]:
            if activity.reason and activity.reason.strip():
                reasons.append(f"{activity.day_date} {activity.planned_start_time:%H:%M} · {names[str(activity.place_candidate_id)]}：{activity.reason.strip()[:300]}")
        if not reasons:
            return None
        return {"revision_id": str(row.id), "run_id": str(row.run_id), "trip_version": row.trip_version,
                "status": status, "reasons": reasons[:10], "model_notes_verified": False}
    return None
