"""Capability-limited context loader: SELECT only, never Planning context repair."""
import re

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.companion_contracts import CompanionContext, CompanionExplanation, EntityReference, InformationNeed
from app.database import Activity, DayPlan, PlaceCandidate, PlanningRun, PlanRevision, Trip, TripPreferences


class CompanionContextReader:
    def __init__(self, session: AsyncSession, trip_id):
        self._session, self._trip_id = session, trip_id

    async def _select(self, query):
        # Loading must not flush unrelated pending ORM changes either.
        return await self._session.execute(query, execution_options={"autoflush": False})

    async def load(self, context: CompanionContext, need: InformationNeed) -> CompanionContext:
        if not self._trip_id:
            return context
        changes = {}
        if need.trip_context_required:
            row = (await self._select(select(Trip.title, Trip.destination)
                .where(Trip.id == self._trip_id))).first()
            if row:
                changes["trip_summary"] = {"title": row.title, "destination": row.destination}
                changes["current_destination"] = context.current_destination or row.destination
        if need.preferences_required:
            row = (await self._select(select(TripPreferences.pace, TripPreferences.interest_categories,
                TripPreferences.avoid_categories, TripPreferences.free_text_requirements)
                .where(TripPreferences.trip_id == self._trip_id))).first()
            if row:
                changes["saved_trip_preferences"] = dict(row._mapping)
        if need.itinerary_required:
            # Exact display mentions narrow reads; ambiguous duplicate names
            # remain a list. We never pick a guessed formal identity.
            mention = re.search(r"(?:把|将)(.{1,40}?)(?:安排|放|排|改)", context.current_message)
            query = select(Activity.id, Activity.custom_name, PlaceCandidate.name, DayPlan.date,
                Activity.scheduled_time).join(DayPlan, Activity.day_plan_id == DayPlan.id)
            query = query.join(PlaceCandidate, Activity.place_candidate_id == PlaceCandidate.id)
            query = query.where(DayPlan.trip_id == self._trip_id)
            if mention:
                name = mention[1].strip()
                query = query.where(or_(PlaceCandidate.name == name, Activity.custom_name == name))
            rows = (await self._select(query.order_by(DayPlan.date, Activity.scheduled_time).limit(10))).all()
            changes["formal_itinerary_summary"] = [{"subject_ref": EntityReference(kind="formal_activity", value=str(r.id)).model_dump(),
                "name": r.custom_name or r.name, "date": str(r.date), "time": str(r.scheduled_time)} for r in rows]
            if need.decision_history_required and len(rows) == 1:
                rationale = await self._validated_rationale(rows[0])
                if rationale:
                    changes["referenced_decision"] = rationale
        return context.model_copy(update=changes)

    async def _validated_rationale(self, activity):
        # Only an accepted revision for the CURRENT formal version can explain
        # an exactly identified surviving Activity. Invalid/shadow/unavailable
        # prose, pending candidates and old versions do not confer authority.
        row = (await self._select(select(PlanRevision.id,
            PlanRevision.difference_summary["decision_summary"].label("summary"))
            .join(PlanningRun, PlanningRun.id == PlanRevision.planning_run_id)
            .join(Trip, Trip.id == PlanRevision.trip_id)
            .where(Trip.id == self._trip_id, PlanRevision.status == "accepted", PlanningRun.status == "accepted",
                PlanningRun.base_trip_version == Trip.version - 1)
            .order_by(PlanRevision.decided_at.desc(), PlanRevision.created_at.desc()).limit(1))).first()
        summary = row.summary if row else None
        if not isinstance(summary, dict) or summary.get("status") != "validated" or summary.get("error_codes"):
            return None
        if not isinstance(summary.get("entries"), list):
            return None
        entries = [entry for entry in summary.get("entries", []) if isinstance(entry, dict)
            and entry.get("target_activity_id") == str(activity.id) and entry.get("evidence_status") == "validated"
            and isinstance(entry.get("after"), dict)
            and entry.get("after", {}).get("start_time") == str(activity.scheduled_time)[:5]
            and isinstance(entry.get("reason"), str) and entry["reason"].strip()]
        if not entries:
            return None
        return CompanionExplanation(subject_ref=EntityReference(kind="formal_activity", value=str(activity.id)),
            explanation_type="original_validated_decision", reasons=list(dict.fromkeys(e["reason"] for e in entries))[:10],
            based_on_prior_decision=True, source_decision_ref=f"revision:{row.id}",
            fact_freshness_warning="这是该已接受版本中通过验证并保存的决定理由，不代表实时事实。")
