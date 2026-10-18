"""Explicit Companion-to-Draft requirement handoff using the existing owner/CAS."""
import asyncio
import re
from uuid import UUID, uuid5

from app.drafts.repository import DraftError
from app.drafts.service import draft_records
from app.requirements import RequirementScope, capture_explicit_requirements, valid_records

_IMPORT_NAMESPACE = UUID("67f20cb2-cfa6-4d4c-a510-a1c05757f5fa")


async def sync_draft_requirements(envelope, message, message_id, messages, port):
    if not envelope.read_draft_id:
        return envelope, None
    repository, owner = getattr(port, "draft_repository", None), getattr(port, "owner", None)
    if repository is None or not owner:
        return envelope, {"status": "unavailable", "reason": "trusted_draft_boundary_unavailable"}
    try:
        draft = await asyncio.to_thread(repository.get, owner, envelope.read_draft_id)
    except DraftError:
        return envelope, {"status": "unavailable", "reason": "draft_not_found"}
    records = draft_records(draft)
    canonical = envelope.model_copy(update={"requirement_records": records})
    if envelope.browsing_city and envelope.browsing_city.removesuffix("市") != draft.city.removesuffix("市"):
        return canonical, {"status": "scope_mismatch"}
    scope = {"kind": "draft", "draft_id": str(draft.id), "city": draft.city}
    explicit_import = bool(re.search(r"(?:把|将).*(?:刚才|当前话题).*(?:要求|偏好).*(?:加入|保存|带入).*草稿", message))
    if explicit_import:
        # Explicit selection binds one latest Topic snapshot, never all prose or
        # arbitrary historical sessions. Source IDs stay attached to each atom.
        latest = next((m.get("context") for m in reversed(messages) if isinstance(m.get("context"), dict)
            and m["context"].get("topic_id") == envelope.topic_id), None)
        if not latest or latest.get("read_trip_id") or latest.get("read_draft_id"):
            return canonical, {"status": "source_unavailable"}
        source_city = latest.get("browsing_city")
        if not source_city or source_city.removesuffix("市") != draft.city.removesuffix("市"):
            return canonical, {"status": "scope_mismatch"}
        # Transfer the scoped record graph, including localized tombstones. A
        # broad-only projection would silently lose both day requirements and
        # the exception that revokes a broad requirement on just one day.
        source = [r for r in valid_records(latest.get("requirement_records", []))
            if not r["scope"].get("trip_id") and not r["scope"].get("draft_id")
            and r["scope"].get("topic_id") in {None, envelope.topic_id}
            and (not r["scope"].get("city") or r["scope"]["city"].removesuffix("市") == draft.city.removesuffix("市"))]
        if any(r["scope"].get("date") or r["scope"].get("activity_id")
                or (r["scope"].get("day_index") or 0) > draft.day_count for r in source):
            return canonical, {"status": "scope_out_of_range", "message": "话题要求包含草稿之外的日期或活动，请明确调整范围后再导入。"}
        identities = {r["id"]: "req_" + uuid5(_IMPORT_NAMESPACE, f"{draft.id}:{r['id']}").hex for r in source}
        existing_ids = {r["id"] for r in records}
        for record in source:
            if identities[record["id"]] in existing_ids:
                continue  # Re-import cannot reactivate a Draft-revoked record.
            target_scope = RequirementScope.model_validate({**scope,
                "kind": "day" if record["scope"].get("day_index") else "draft",
                "day_index": record["scope"].get("day_index")}).model_dump(mode="json")
            copied = {**record, "id": identities[record["id"]], "scope": target_scope,
                "supersedes": [identities[old] for old in record["supersedes"] if old in identities]}
            if copied["status"] == "active" and copied["key"] != "user_requirement":
                for prior in records:
                    same_dimension = copied["key"] not in {"interest", "avoid_category"} or prior["value"] == copied["value"]
                    if prior["status"] == "active" and prior["scope"] == target_scope and prior["key"] == copied["key"] and same_dimension:
                        prior["status"] = "superseded"
                        copied["supersedes"].append(prior["id"])
            records.append(copied)
    else:
        records = capture_explicit_requirements(records, message, scope=scope, source_ref=str(message_id))
    if records == draft_records(draft):
        return canonical, {"status": "unchanged", "draft_version": draft.version}
    if envelope.read_draft_version is None or draft.version != envelope.read_draft_version:
        return canonical, {"status": "version_conflict", "draft_version": draft.version}
    def apply(current):
        if current.status != "active" or any(run.status == "running" for run in current.runs):
            raise DraftError("draft_not_editable")
        current.requirement_records = records
    try:
        changed = await asyncio.to_thread(repository.mutate, owner, draft.id, envelope.read_draft_version, apply)
    except DraftError as exc:
        return canonical, {"status": "version_conflict", "reason": exc.code}
    return envelope.model_copy(update={"requirement_records": records, "read_draft_version": changed.version}), {
        "status": "saved", "draft_version": changed.version, "record_ids": [r["id"] for r in records if r["status"] == "active"]}
