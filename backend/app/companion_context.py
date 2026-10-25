"""Capability-limited context loader: SELECT only, never Planning context repair."""
import re
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.companion_contracts import CompanionContext, CompanionExplanation, EntityReference, InformationNeed
from app.database import PlanningRun, PlanRevision, Trip, TripPreferences


class CompanionContextReader:
    def __init__(self, session: AsyncSession, trip_id, *, read_snapshot=None):
        self._session, self._trip_id, self._read_snapshot = session, trip_id, read_snapshot

    async def _select(self, query):
        # Loading must not flush unrelated pending ORM changes either.
        return await self._session.execute(query, execution_options={"autoflush": False})

    async def load(self, context: CompanionContext, need: InformationNeed) -> CompanionContext:
        if not self._trip_id:
            return context.model_copy(update={'displayed_revision':None})
        if self._read_snapshot and self._read_snapshot.trip['id'] != str(self._trip_id):
            raise ValueError('读取快照与旅行不一致。')
        changes = {'displayed_revision':None}
        snapshot = self._read_snapshot
        if snapshot and snapshot.displayed_revision:
            # A validated, displayed working copy remains read context even
            # when the semantic selector labels its follow-up as consultation.
            # Never look up a latest pending revision or manufacture authority.
            from copy import deepcopy
            changes['displayed_revision'] = deepcopy(snapshot.displayed_revision)
        itinerary_read = (need.itinerary_required or need.decision_history_required
            or re.search(r"已选|备选|留白|未排程|我的安排|选了什么", context.current_message))
        if itinerary_read and snapshot is None:
            from app.saved_trip_reads import load_saved_trip_read
            snapshot = await load_saved_trip_read(self._session, self._trip_id, context.current_message)
        if need.trip_context_required:
            if snapshot:
                changes['trip_summary'] = dict(snapshot.trip)
                changes['current_destination'] = context.current_destination or snapshot.trip['destination']
            else:
                row = (await self._select(select(Trip.id, Trip.version, Trip.title, Trip.destination)
                    .where(Trip.id == self._trip_id))).first()
                if row:
                    changes["trip_summary"] = {"id": str(row.id), "version": row.version, "title": row.title, "destination": row.destination}
                    changes["current_destination"] = context.current_destination or row.destination
        if need.preferences_required and not (context.assistant_context and context.assistant_context.get("browsing_city")
            and context.assistant_context.get("browsing_city").rstrip("市") != changes.get("trip_summary", {}).get("destination", "").rstrip("市")):
            if snapshot:
                from copy import deepcopy
                changes['saved_trip_preferences'] = deepcopy(snapshot.preferences)
            else:
                row = (await self._select(select(TripPreferences.pace, TripPreferences.interest_categories,
                    TripPreferences.avoid_categories, TripPreferences.free_text_requirements)
                    .where(TripPreferences.trip_id == self._trip_id))).first()
                if row:
                    changes["saved_trip_preferences"] = dict(row._mapping)
        if itinerary_read:
            projection = snapshot.project(context.current_message)
            rows = projection['activities']
            changes['formal_itinerary_summary'] = rows
            changes['arrangement_items'] = projection['arrangement_items']
            changes['itinerary_read_coverage'] = projection['coverage']
            if (need.decision_history_required and len(rows) == 1 and not projection['coverage']['ambiguous']
                and (rows[0]['name'] in context.current_message or projection['coverage']['scope_kind'] == 'activity')
                and not re.search(r"候选|待确认|新方案", context.current_message)):
                rationale = await self._validated_rationale(SimpleNamespace(id=UUID(rows[0]['activity_id']), scheduled_time=rows[0]['time']),
                    captured_version=snapshot.trip['version'])
                if rationale:
                    changes["referenced_decision"] = rationale
        if need.decision_history_required and not context.resolved_entities:
            from app.saved_plan_notes import read_saved_plan_notes
            expected = snapshot.trip['version'] if snapshot else None
            await self._assert_captured_version(expected)
            changes["saved_plan_notes"] = await read_saved_plan_notes(self._session, self._trip_id, context.current_message)
            await self._assert_captured_version(expected)
        return context.model_copy(update=changes)

    async def _assert_captured_version(self, expected):
        if expected is not None:
            current = (await self._select(select(Trip.version).where(Trip.id == self._trip_id))).scalar_one_or_none()
            if current != expected:
                from app.saved_trip_reads import SavedTripReadStale
                raise SavedTripReadStale('安排已更新，请重新读取后查询原始理由。')

    async def _validated_rationale(self, activity, *, captured_version=None):
        # Only an accepted revision for the CURRENT formal version can explain
        # an exactly identified surviving Activity. Invalid/shadow/unavailable
        # prose, pending candidates and old versions do not confer authority.
        await self._assert_captured_version(captured_version)
        row = (await self._select(select(PlanRevision.id,
            PlanRevision.difference_summary["decision_summary"].label("summary"))
            .join(PlanningRun, PlanningRun.id == PlanRevision.planning_run_id)
            .join(Trip, Trip.id == PlanRevision.trip_id)
            .where(Trip.id == self._trip_id, PlanRevision.status == "accepted", PlanningRun.status == "accepted",
                PlanningRun.base_trip_version == Trip.version - 1)
            .where(Trip.version == captured_version if captured_version is not None else True)
            .order_by(PlanRevision.decided_at.desc(), PlanRevision.created_at.desc()).limit(1))).first()
        await self._assert_captured_version(captured_version)
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
