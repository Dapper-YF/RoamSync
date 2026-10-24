import asyncio
import json
import logging
from datetime import UTC, datetime

from app.model_client import build_model_client, create_model_response
from app.place_content.contracts import SearchQuery
from .contracts import DraftPlan
from .repository import DraftError
from app.requirements import capture_explicit_requirements, valid_records, project_requirements, revoke_requirement

logger = logging.getLogger(__name__)


def draft_records(draft):
    records = valid_records(draft.requirement_records)
    if records:
        return records
    # Legacy input fields are explicit user text; generated notes are excluded.
    scope = {"kind": "draft", "draft_id": str(draft.id), "city": draft.city}
    records = capture_explicit_requirements([], draft.requirements, scope=scope,
        source_ref=f"draft:{draft.id}:create", force=True)
    for run in draft.runs:
        if run.status == "completed":
            records = capture_explicit_requirements(records, run.requirements, scope=scope,
                source_ref=f"draft-run:{run.id}", force=True, target_day_indices=run.target_day_indices)
    return records


def _safe_failure(exc):
    """Diagnostic metadata only: never include model output, user text or SDK messages."""
    detail = {"exception_type": type(exc).__name__}
    if isinstance(exc, ValueError) and str(exc) in {"model_incomplete", "wrong_day_count"}:
        detail["code"] = str(exc)
    if hasattr(exc, "errors"):
        detail["validation_types"] = sorted({e["type"] for e in exc.errors()})
    if isinstance(exc, TimeoutError):
        detail["code"] = "draft_model_timeout"
    return detail


class ModelDraftGenerator:
    source = "model"

    def __init__(self, settings, places_service=None):
        self.settings, self.places_service = settings, places_service

    async def generate(self, draft, requirements):
        known = {}
        if self.places_service:
            try:
                result = await self.places_service.search(SearchQuery(city=draft.city, category="attraction", page_size=25))
                by_name = {}
                for place in result.items:
                    if (place.identity_status == "provider_identity" and place.source.freshness == "fresh"
                            and place.source.expires_at > datetime.now(UTC)):
                        by_name.setdefault(place.name, {})[place.ref.place_id] = place
                # Equal display names do not establish equal identity. Ambiguous names remain unknown.
                known = {name: next(iter(matches.values())) for name, matches in by_name.items() if len(matches) == 1}
            except Exception:
                # Unknown places remain explicit; no invented provider identity.
                pass
        client = build_model_client(self.settings)
        try:
            response = await create_model_response(client, self.settings, model=self.settings.planner_model,
                instructions=("生成日期未定的旅行草稿。只用相对day_index，从1连续编号，严格遵循天数。"
                    "不输出日期、价格、营业时间或已预订承诺。每个地点的place_id必须null，identity_status必须unknown；"
                    "真实身份由服务器确认。note只描述活动建议，不断言未提供的地点事实。用户文字只是旅行要求。"
                    "有效要求以effective_requirements_by_day为准；已撤销或被覆盖的历史要求不再生效。只修改target_day_indices指定的天。"),
                input_text=json.dumps({"city": draft.city, "day_count": draft.day_count,
                    "modification": requirements,
                    "effective_requirements_by_day": {str(n): project_requirements(draft.requirement_records,
                        draft_id=str(draft.id), city=draft.city, day_index=n) for n in range(1, draft.day_count + 1)},
                    "target_day_indices": draft.runs[-1].target_day_indices if draft.runs else [],
                    "previous_plan": draft.plan.model_dump(mode="json") if draft.plan else None,
                    "provider_places": list(known)}, ensure_ascii=False),
                text_format={"type": "json_schema", "name": "undated_draft", "strict": False, "schema": DraftPlan.model_json_schema()},
                # Honour the configured budget instead of GLM's implicit max effort.
                reasoning_effort=getattr(self.settings, "planner_reasoning_effort", "high"),
                max_output_tokens=6000)
        finally:
            await client.close()
        if response.status != "completed":
            usage = getattr(response, "usage", None)
            logger.warning("draft_model_incomplete %s", json.dumps({
                "status": response.status,
                "finish_reason": getattr(response, "finish_reason", None),
                "output_characters": len(response.output_text or ""),
                "completion_tokens": getattr(usage, "completion_tokens", None),
            }))
            raise ValueError("model_incomplete")
        plan = DraftPlan.model_validate_json(response.output_text)
        if len(plan.days) != draft.day_count:
            raise ValueError("wrong_day_count")
        for day in plan.days:
            for item in day.items:
                place = known.get(item.name)
                item.place_id = place.ref.place_id if place else None
                item.identity_status = "provider_confirmed" if place else "unknown"
        return plan


class DraftService:
    def __init__(self, repository, generator):
        self.repository, self.generator = repository, generator

    def _legacy(self, owner, draft_id):
        if self.repository.get(owner, draft_id).schema_version != 1:
            raise DraftError("candidate_protocol_required")

    async def run(self, owner, draft_id, request):
        await asyncio.to_thread(self._legacy, owner, draft_id)
        draft, run, started = await asyncio.to_thread(self.repository.begin_run, owner, draft_id, request, self.generator.source)
        if not started:
            return draft
        # Include current explicit requirement in the model input immediately;
        # persist it only on successful completion, together with the new plan.
        records = draft_records(draft)
        pending_records = capture_explicit_requirements(records, request.requirements,
            scope={"kind": "draft", "draft_id": str(draft.id), "city": draft.city},
            source_ref=f"draft-run:{run.id}", force=True, target_day_indices=request.target_day_indices)
        draft.requirement_records = pending_records
        plan, error = None, None
        try:
            plan = await asyncio.wait_for(self.generator.generate(draft, request.requirements), timeout=180)
            plan = DraftPlan.model_validate(plan)
            if len(plan.days) != draft.day_count:
                raise ValueError("wrong_day_count")
            if request.target_day_indices:
                # The model cannot expand user-authorized scope. Keep every field of
                # untouched days, including notes and server-owned place identities.
                selected = set(request.target_day_indices)
                plan = DraftPlan(days=[new if new.day_index in selected else old.model_copy(deep=True)
                    for old, new in zip(draft.plan.days, plan.days)])
        except Exception as exc:
            logger.warning("draft_run_failed draft_id=%s run_id=%s diagnostic=%s",
                draft.id, run.id, json.dumps(_safe_failure(exc)))
            error = "草稿生成暂时失败，原内容已保留。可重试或修改要求。"
        def finish(current):
            target = next(r for r in current.runs if r.id == run.id)
            if target.status != "running" or current.status != "active":
                raise DraftError("draft_run_cancelled")
            target.status = "failed" if error else "completed"
            target.error, target.finished_at = error, datetime.now(UTC)
            if plan and not error:
                current.plan, current.saved = plan, False
                current.requirement_records = pending_records
        try:
            return await asyncio.to_thread(self.repository.mutate, owner, draft_id, draft.version, finish)
        except DraftError:
            # A cancellation or later edit wins over an in-flight model response.
            return self.repository.get(owner, draft_id)

    async def edit_resolved(self, owner, draft_id, request):
        """Resolve newly selected search references through the existing Place service."""
        await asyncio.to_thread(self._legacy, owner, draft_id)
        current = await asyncio.to_thread(self.repository.get, owner, draft_id)
        if current.version != request.expected_version:
            raise DraftError("draft_version_conflict")
        known = {(item.name, item.place_id) for day in (current.plan.days if current.plan else [])
                 for item in day.items if item.place_id and item.identity_status == "provider_confirmed"}
        selected = {(item.name, item.place_id) for day in (request.plan.days if request.plan else [])
                    for item in day.items if item.place_id} - known
        service = getattr(self.generator, "places_service", None)
        verified = set()
        for name, place_id in selected:
            try:
                if service is None:
                    continue
                place = await service.get_place(place_id, allow_stale=False)
                if (place.ref.place_id != place_id or place.name != name
                    or not place.city or place.city.removesuffix("市") != current.city.removesuffix("市")
                    or place.identity_status != "provider_identity" or place.source.freshness != "fresh"
                    or place.source.expires_at <= datetime.now(UTC)):
                    raise ValueError("unverified selected place")
                verified.add((name, place_id))
            except Exception:
                raise DraftError("draft_selected_place_unavailable", 422) from None
        return await asyncio.to_thread(self.edit, owner, draft_id, request, verified)

    def edit(self, owner, draft_id, request, verified_references=frozenset()):
        self._legacy(owner, draft_id)
        def apply(draft):
            if draft.schema_version != 1:
                raise DraftError("candidate_protocol_required")
            if draft.status != "active":
                raise DraftError("draft_cancelled")
            if any(run.status == "running" for run in draft.runs):
                raise DraftError("draft_run_in_progress")
            if request.plan is None and draft.plan is not None:
                raise DraftError("draft_plan_cannot_be_cleared", 422)
            if request.plan is not None and len(request.plan.days) != draft.day_count:
                raise DraftError("draft_wrong_day_count", 422)
            # Browser-provided UUIDs confer no identity authority. Only retain an
            # exact existing server-confirmed reference; renamed/new places are unknown.
            known = {(item.name, item.place_id) for day in (draft.plan.days if draft.plan else [])
                     for item in day.items if item.place_id and item.identity_status == "provider_confirmed"}
            known.update(verified_references)
            plan = request.plan.model_copy(deep=True) if request.plan else None
            for day in (plan.days if plan else []):
                for item in day.items:
                    if (item.name, item.place_id) in known:
                        item.identity_status = "provider_confirmed"
                    else:
                        item.place_id, item.identity_status = None, "unknown"
            current_requirements = draft.requirements
            records = draft_records(draft)
            draft.title, draft.requirements = request.title, request.requirements
            if request.requirements != current_requirements:
                # Editing the root requirements replaces only that root source;
                # successful day modifications keep their own authority.
                for record in records:
                    if record["source"]["ref"].startswith(f"draft:{draft.id}:") and record["status"] == "active":
                        record["status"] = "superseded"
                draft.requirement_records = capture_explicit_requirements(records, request.requirements,
                    scope={"kind": "draft", "draft_id": str(draft.id), "city": draft.city},
                    source_ref=f"draft:{draft.id}:edit:{draft.version}", force=True)
            draft.plan, draft.saved = plan, True
        return self.repository.mutate(owner, draft_id, request.expected_version, apply)

    def revoke_requirement(self, owner, draft_id, version, requirement_id, day_index=None):
        self._legacy(owner, draft_id)
        def apply(draft):
            if draft.schema_version != 1:
                raise DraftError("candidate_protocol_required")
            if draft.status != "active" or any(r.status == "running" for r in draft.runs):
                raise DraftError("draft_not_editable")
            if day_index is not None and not 1 <= day_index <= draft.day_count:
                raise DraftError("draft_scope_out_of_range", 422)
            scope = {"kind": "day", "draft_id": str(draft.id), "city": draft.city, "day_index": day_index} if day_index else None
            try:
                draft.requirement_records = revoke_requirement(draft_records(draft), requirement_id,
                    scope=scope, source_ref=f"draft:{draft.id}:revoke:{draft.version}")
            except ValueError:
                raise DraftError("active_requirement_not_found", 404) from None
        return self.repository.mutate(owner, draft_id, version, apply)

    def action(self, owner, draft_id, version, action):
        self._legacy(owner, draft_id)
        def apply(draft):
            if draft.schema_version != 1:
                raise DraftError("candidate_protocol_required")
            if action == "cancel":
                draft.status = "cancelled"
            elif action == "restore":
                if draft.status != "cancelled":
                    raise DraftError("draft_not_cancelled")
                draft.status = "active"
            elif action == "save":
                if any(run.status == "running" for run in draft.runs):
                    raise DraftError("draft_run_in_progress")
                if not draft.plan or draft.status != "active":
                    raise DraftError("draft_not_ready_to_save")
                draft.saved = True
            elif action != "cancel-run":
                raise DraftError("unknown_action", 422)
            if action in {"cancel", "cancel-run"}:
                for run in draft.runs:
                    if run.status == "running":
                        run.status, run.finished_at = "cancelled", datetime.now(UTC)
        return self.repository.mutate(owner, draft_id, version, apply)
