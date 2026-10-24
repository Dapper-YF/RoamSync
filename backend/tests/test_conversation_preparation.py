"""Deterministic provider fixtures; no database connections or model calls."""
import asyncio
import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.drafts.contracts import Draft, DraftDay, DraftPlan, DraftScheduleConstraints
from app.draft_promotion.contracts import PreviewRequest, PreparedPlan, Operation
from app.draft_promotion.preparation import prepare, valid_hashes, semantic_values, evidence_values, digest, refresh_equivalent
from app.place_content.contracts import Image, Place, RouteResult


class Places:
    def __init__(self):
        now = datetime.now(UTC)
        self.items = [Place(ref={"place_id": UUID(int=n), "external_ref": {"provider_place_id": f"POI{n}"}},
            name=f"地点{n}", city="杭州", category="attraction",
            location={"longitude": 120 + n / 1000, "latitude": 30},
            source={"source_url": f"https://fixture.invalid/{n}", "fetched_at": now,
                "expires_at": now + timedelta(hours=1)}) for n in (1, 2)]
        self.route_queries = []

    async def get_place(self, place_id, **_):
        return next(p for p in self.items if p.ref.place_id == place_id)

    async def query_route(self, query):
        self.route_queries.append(query)
        now = datetime.now(UTC)
        return RouteResult(origin=query.origin, destination=query.destination, mode=query.mode,
            distance_meters=800, duration_seconds=600, path=[query.origin, query.destination],
            source={"source_url": "https://fixture.invalid/route", "fetched_at": now,
                "expires_at": now + timedelta(hours=1)})


def candidate(places, **schedule):
    return Draft(id=uuid4(), schema_version=2, title="午餐和慢游", city="杭州", day_count=1,
        requirements="", version=1, status="active", saved=False, runs=[], updated_at=datetime.now(UTC),
        plan={"schema_version": 2, "schedule_constraints": {"start_date": "2026-11-01",
            "daily_start_time": "09:00", "daily_end_time": "18:00", "transport_mode": "walk", **schedule},
            "days": [{"day_index": 1, "title": "第一天", "items": [
                {"item_ref": "park", "name": places.items[0].name, "place_id": places.items[0].ref.place_id,
                    "provider_place_id": "POI1", "identity_status": "provider_confirmed", "kind": "visit",
                    "duration_minutes": 120, "duration_source": "user_explicit", "source_quote": "公园玩两小时"},
                {"item_ref": "lunch", "name": "午餐", "kind": "meal", "start_time": "12:00", "end_time": "13:00",
                    "source_quote": "中午留一小时吃饭"},
                {"item_ref": "street", "name": places.items[1].name, "place_id": places.items[1].ref.place_id,
                    "provider_place_id": "POI2", "identity_status": "provider_confirmed", "kind": "visit",
                    "duration_minutes": 90},
                {"item_ref": "maybe", "name": "有空喝茶", "kind": "optional"}]}]})


def preview(draft, places):
    return asyncio.run(prepare(draft, PreviewRequest(expected_version=1, start_date="2026-11-01"), places))


def test_allocated_lunch_can_move_after_longer_visit_but_explicit_window_cannot():
    places=Places()
    draft=candidate(places)
    draft.plan.days[0].items=draft.plan.days[0].items[:3]
    draft.plan.days[0].items[0].duration_minutes=210
    plan=preview(draft,places)
    lunch=plan.windows[0]
    assert (lunch.start_time,lunch.end_time)==(time(12,30),time(13,30))
    assert not any("重叠" in issue for issue in plan.coverage.blockers)
    draft.plan.days[0].items[1].source_quote="12:00到13:00必须留空吃饭"
    fixed=preview(draft,places)
    assert any("重叠" in issue for issue in fixed.coverage.blockers)


def test_v2_preparation_preserves_duration_windows_optional_and_real_route():
    places = Places()
    plan = preview(candidate(places), places)
    assert plan.schema_version == 2 and valid_hashes(plan)
    assert not plan.coverage.blockers
    assert [(a.ref, a.duration_minutes, a.planned_start_time, a.end_time) for a in plan.activities] == [
        ("park", 120, time(9), time(11)), ("street", 90, time(13, 10), time(14, 40))]
    assert [(w.ref, w.kind, w.start_time, w.end_time) for w in plan.windows] == [
        ("lunch", "meal", time(12), time(13)), ("maybe", "optional", None, None)]
    assert [(r.from_ref, r.to_ref, r.route.duration_seconds) for r in plan.routes] == [("park", "street", 600)]
    assert len(places.route_queries) == 1


@pytest.mark.parametrize("mutation", ["title", "name", "note", "window", "source"])
def test_v2_display_and_window_tampering_breaks_hash(mutation):
    places = Places()
    plan = preview(candidate(places), places)
    if mutation == "title":
        plan.title += "改"
    elif mutation in {"name", "note"}:
        setattr(plan.activities[0], mutation, "改")
    elif mutation == "window":
        plan.windows[0].end_time = time(13, 1)
    else:
        plan.activities[0].source_quote += "改"
    assert not valid_hashes(plan)


def test_v2_blank_day_preserved_and_unsupported_transport_blocks():
    places = Places()
    draft = candidate(places, transport_mode="transit")
    plan = preview(draft, places)
    assert any("交通" in b for b in plan.coverage.blockers)
    draft.plan.days[0].items = [draft.plan.days[0].items[1].model_copy(update={
        "kind": "blank_day", "name": "整天留白", "start_time": None, "end_time": None})]
    draft.plan.schedule_constraints.transport_mode = "walk"
    plan = preview(draft, places)
    assert not plan.coverage.blockers and not plan.activities
    assert [(w.kind, w.start_time, w.end_time) for w in plan.windows] == [("blank_day", time(9), time(18))]


def test_v2_overlap_unknown_identity_and_unverified_hard_requirement_block():
    places = Places()
    draft = candidate(places)
    draft.plan.days[0].items[0].start_time = time(11)
    draft.plan.days[0].items[0].end_time = time(13)
    draft.plan.days[0].items[1].source_quote = "午餐必须12:00到13:00"
    draft.plan.days[0].items[2].provider_place_id = "WRONG"
    draft.requirement_records = [{"id": "hard", "text": "必须无过敏原", "key": "user_requirement", "value": None,
        "source": {"kind": "user_explicit", "ref": "message:1"},
        "scope": {"kind": "draft", "draft_id": str(draft.id), "city": "杭州"},
        "strength": "hard", "status": "active", "supersedes": []}]
    plan = preview(draft, places)
    assert any("重叠" in b for b in plan.coverage.blockers)
    assert any("身份" in b for b in plan.coverage.blockers)
    assert any("必须无过敏原" in b for b in plan.coverage.blockers)
    assert [(c.requirement_ref, c.status, c.source_ref) for c in plan.constraint_checks] == [("hard", "unverified", "message:1")]


def test_versioned_contract_rejects_silent_v2_downgrade_and_duplicate_refs():
    places = Places()
    payload = candidate(places).plan.model_dump(mode="json")
    payload["schema_version"] = 1
    with pytest.raises(ValidationError):
        DraftPlan.model_validate(payload)
    payload["schema_version"] = 2
    payload["days"][0]["items"][1]["item_ref"] = "park"
    with pytest.raises(ValidationError):
        DraftPlan.model_validate(payload)


def test_v2_window_duration_source_and_long_title_never_disappear():
    places = Places()
    draft = candidate(places)
    draft.title = "长" * 121
    lunch = draft.plan.days[0].items[1]
    lunch.duration_source = "user_explicit"
    plan = preview(draft, places)
    assert plan.title == draft.title
    assert plan.windows[0].duration_minutes == 60
    assert plan.windows[0].duration_source == "user_explicit"
    assert any("标题" in b for b in plan.coverage.blockers)


def test_v2_rejects_unknown_requirement_records_instead_of_dropping_them():
    payload = candidate(Places()).model_dump(mode="json")
    payload["requirement_records"] = [{"text": "必须无过敏原", "strength": "hard"}]
    with pytest.raises(ValidationError):
        Draft.model_validate(payload)


def test_v2_refresh_failure_does_not_claim_trip_was_created():
    places = Places()
    plan = preview(candidate(places), places)
    places.items = []
    result, error = asyncio.run(refresh_equivalent(plan, places))
    assert result is None and "已创建" not in error


def test_v1_golden_hash_bytes_survive_new_default_fields_without_db():
    places = Places()
    for n, place in enumerate(places.items):
        place.ref.place_id = UUID(f"00000000-0000-4000-8000-{n+2:012d}")
        place.ref.external_ref.provider_place_id = str(n)
        place.name = f"测试地点{n}"
        place.location.longitude = 120 + n / 1000
        place.source.source_url = f"https://fixture.invalid/{n}"
    original_route = places.query_route
    async def route(query):
        result = await original_route(query)
        result.distance_meters = 600
        return result
    places.query_route = route
    draft = Draft(id=UUID("00000000-0000-4000-8000-000000000001"), title="旧标题", city="杭州", day_count=1,
        requirements="", version=2, status="active", saved=False, runs=[], updated_at=datetime.now(UTC),
        plan={"days": [{"day_index": 1, "title": "旧一天", "items": [
            {"name": p.name, "place_id": p.ref.place_id, "identity_status": "provider_confirmed"} for p in places.items]}]})
    plan = asyncio.run(prepare(draft, PreviewRequest(expected_version=2, start_date="2026-11-01"), places))
    fixture = json.loads((Path(__file__).parents[1] / "evals/fixtures/draft_promotion_golden_v1.json").read_text(encoding="utf-8"))
    assert semantic_values(plan) == fixture["semantic"]
    assert evidence_values(plan) == fixture["evidence"]
    assert digest(semantic_values(plan)) == fixture["content_hash"]
    assert digest(evidence_values(plan)) == fixture["evidence_hash"]


def test_v2_reviewed_media_changes_invalidate_evidence_on_refresh():
    places = Places()
    plan = preview(candidate(places), places)
    changed = places.items[0].model_copy(deep=True)
    changed.image_status = "available"
    changed.images = [Image(url="/new.webp", source_url="https://commons.wikimedia.org/wiki/File:New.jpg",
        attribution="Fixture", usage_basis="CC0", place_ref=changed.ref)]
    places.items[0] = changed
    result, error = asyncio.run(refresh_equivalent(plan, places))
    assert result is None and "变化" in error


def test_v2_duplicate_canonical_and_provider_identities_both_block():
    places = Places()
    draft = candidate(places)
    second = draft.plan.days[0].items[2]
    first = draft.plan.days[0].items[0]
    second.place_id, second.provider_place_id, second.name = first.place_id, first.provider_place_id, first.name
    assert any("重复" in b for b in preview(draft, places).coverage.blockers)
    places = Places()
    places.items[1].ref.external_ref.provider_place_id = "POI1"
    draft = candidate(places)
    draft.plan.days[0].items[2].provider_place_id = "POI1"
    assert any("重复" in b for b in preview(draft, places).coverage.blockers)


@pytest.mark.parametrize("field,value", [("address", "地址更改"), ("experience", {
    "summary": "已审核的新描述", "attributes": [], "source_url": "https://fixture.invalid/facts",
    "source_title": "参考资料", "reviewed_at": "2026-10-24", "unknown": [], "scope": "venue"})])
def test_v2_display_facts_refresh_requires_new_confirmation(field, value):
    places = Places()
    plan = preview(candidate(places), places)
    updated = places.items[0].model_dump(mode="json")
    updated[field] = value
    places.items[0] = Place.model_validate(updated)
    result, error = asyncio.run(refresh_equivalent(plan, places))
    assert result is None and "变化" in error


@pytest.mark.parametrize("schedule", [{"max_walking_minutes": 600}, {"total_budget_fen": 100000}, {"daily_budget_fen": 100000}])
def test_unsupported_legacy_constraint_shapes_are_blocked_but_prepared_stays_readable(schedule):
    places = Places()
    plan = preview(candidate(places, **schedule), places)
    assert plan.coverage.blockers
    assert PreparedPlan.model_validate(plan.model_dump(mode="json")).prepared_hash == plan.prepared_hash
    assert plan.schedule_constraints.model_dump(mode="json").items() >= schedule.items()


def test_v1_prepared_plan_rejects_v2_only_activity_values():
    places = Places()
    plan = preview(candidate(places), places)
    payload = plan.model_dump(mode="json")
    payload.update(schema_version=1, schedule_constraints=None, windows=[], constraint_checks=[])
    with pytest.raises(ValidationError):
        PreparedPlan.model_validate(payload)


@pytest.mark.parametrize("version", [True, 1.0, "2", 3])
def test_schema_versions_are_explicit_integer_versions(version):
    payload = candidate(Places()).model_dump(mode="json")
    payload["schema_version"] = version
    with pytest.raises(ValidationError):
        Draft.model_validate(payload)
    payload["plan"]["schema_version"] = version
    with pytest.raises(ValidationError):
        DraftPlan.model_validate(payload["plan"])
    with pytest.raises(ValidationError):
        DraftPlan.model_validate({"schema_version": version, "days": [{"day_index": 1, "title": "历史", "items": []}]})


def test_optional_explicit_times_obey_day_bounds_without_becoming_scheduled():
    places = Places()
    draft = candidate(places)
    draft.plan.days[0].items[-1].start_time = time(19)
    draft.plan.days[0].items[-1].end_time = time(20)
    plan = preview(draft, places)
    assert any("有空喝茶" in b and "可用时间" in b for b in plan.coverage.blockers)
    assert len(plan.activities) == 2


def test_operation_protocol_and_execution_mode_cannot_disagree():
    plan = preview(candidate(Places()), Places())
    fields = dict(id=uuid4(), draft_id=plan.draft_id, draft_version=plan.draft_version,
        prepared_id=plan.id, prepared_hash=plan.prepared_hash, content_hash=plan.content_hash,
        evidence_hash=plan.evidence_hash, allowed_action="create_and_adopt", status="requested",
        stage="authorized", authorized_at=plan.created_at, expires_at=plan.expires_at, updated_at=plan.created_at)
    legacy = Operation(**fields)
    assert (legacy.protocol_version, legacy.execution_mode) == (1, "legacy_checkpoint")
    for overrides in ({"protocol_version": True}, {"protocol_version": 2}, {"execution_mode": "atomic_candidate_v2"}):
        with pytest.raises(ValidationError):
            Operation(**fields, **overrides)


def test_identity_bound_optional_is_blocked_until_formal_identity_mapping_exists():
    places = Places()
    draft = candidate(places)
    optional = draft.plan.days[0].items[-1]
    optional.place_id = places.items[0].ref.place_id
    optional.provider_place_id = places.items[0].ref.external_ref.provider_place_id
    plan = preview(draft, places)
    assert any("备选" in b and "地点身份" in b for b in plan.coverage.blockers)
    window = next(w for w in plan.windows if w.ref == optional.item_ref)
    assert window.place_id == optional.place_id and window.provider_place_id == optional.provider_place_id


def test_per_day_override_is_blocked_and_both_day_bounds_and_title_are_hashed():
    places = Places()
    draft = candidate(places)
    draft.plan.days[0].start_time, draft.plan.days[0].end_time = time(8), time(17)
    plan = preview(draft, places)
    assert any("单独的可用时间" in b for b in plan.coverage.blockers)
    assert (plan.day_constraints[0].start_time, plan.day_constraints[0].end_time) == (time(8), time(17))
    assert plan.schedule_constraints.daily_start_time == time(9)
    plan.day_constraints[0].title += "改"
    assert not valid_hashes(plan)


def test_hard_item_scoped_requirement_cannot_disappear_during_preparation():
    places = Places()
    draft = candidate(places)
    draft.requirement_records = [{"id": "item-hard", "text": "此景点必须保证无障碍", "key": "user_requirement", "value": None,
        "source": {"kind": "user_explicit", "ref": "message:2"},
        "scope": {"kind": "activity", "activity_id": "park", "draft_id": str(draft.id), "city": "杭州"},
        "strength": "hard", "status": "active", "supersedes": []}]
    plan = preview(draft, places)
    assert any("此景点必须保证无障碍" in b for b in plan.coverage.blockers)
    assert any(c.requirement_ref == "item-hard" and c.status == "unverified" for c in plan.constraint_checks)


def test_mixed_timezone_day_bounds_fail_with_validation_error():
    with pytest.raises(ValidationError):
        DraftDay(day_index=1, title="第一天", items=[], start_time="09:00:00+08:00", end_time="18:00")
    with pytest.raises(ValidationError):
        DraftScheduleConstraints(start_date="2026-11-01", daily_start_time="09:00:00+08:00",
            daily_end_time="18:00", transport_mode="walk")


def test_window_cannot_carry_provider_only_identity_or_partial_blank_day_duration():
    payload = candidate(Places()).plan.model_dump(mode="json")
    payload["days"][0]["items"][1]["provider_place_id"] = "POI1"
    with pytest.raises(ValidationError):
        DraftPlan.model_validate(payload)
    payload = candidate(Places()).plan.model_dump(mode="json")
    payload["days"][0]["items"] = [{"name": "整天留白", "kind": "blank_day", "item_ref": "blank", "duration_minutes": 60}]
    with pytest.raises(ValidationError):
        DraftPlan.model_validate(payload)


def test_v2_refs_and_labels_fit_existing_formal_contract():
    places = Places()
    payload = candidate(places).plan.model_dump(mode="json")
    payload["days"][0]["items"][0]["item_ref"] = "p" * 81
    with pytest.raises(ValidationError):
        DraftPlan.model_validate(payload)
    draft = candidate(places)
    draft.plan.days[0].items[1].name = "餐" * 161
    assert any("名称" in b for b in preview(draft, places).coverage.blockers)


@pytest.mark.parametrize("clock", [{"start_time": time(15)}, {"start_time": time(15), "end_time": time(16)}, {"duration_minutes": 60}])
def test_optional_schedule_values_cannot_be_silently_discarded(clock):
    places = Places()
    draft = candidate(places)
    for field, value in clock.items():
        setattr(draft.plan.days[0].items[-1], field, value)
    plan = preview(draft, places)
    assert any("备选" in b and "时间" in b for b in plan.coverage.blockers)


def test_direct_preparation_enforces_formal_requirement_text_limit():
    places = Places()
    draft = candidate(places)
    draft.requirement_records = [{"id": "long", "text": "希望" + "慢" * 2000, "key": "user_requirement", "value": None,
        "source": {"kind": "user_explicit", "ref": "message:3"},
        "scope": {"kind": "draft", "draft_id": str(draft.id), "city": "杭州"},
        "strength": "soft", "status": "active", "supersedes": []}]
    plan = preview(draft, places)
    assert any("2000" in b for b in plan.coverage.blockers)
    assert len(plan.requirements) == 2002
