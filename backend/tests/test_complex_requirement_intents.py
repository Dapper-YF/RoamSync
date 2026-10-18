"""Long formal requests keep plan references distinct from venue identities."""
from datetime import date, time
from types import SimpleNamespace
from uuid import uuid4

from app.planning_intent_service import (
    _ActivityEntity,
    _build_rule_semantic_draft,
    _extract_place_queries,
    _is_non_place_reference,
    _parse_time_scope,
    _resolve_protected_activities,
    _resolve_fixed_activity_reference,
)
from app.requirements import capture_explicit_requirements, project_requirements


def test_long_request_keeps_other_dates_and_revoked_requirement_out_of_places():
    message = (
        "请调整第二天下午的安排，保留其他日期安排不变，"
        "第3天15点固定活动不要动，不要加入第2天已撤销的步行上限。"
    )
    start = date(2026, 10, 16)
    days = [SimpleNamespace(date=start.fromordinal(start.toordinal() + n)) for n in range(3)]
    trip = SimpleNamespace(start_date=start, end_date=days[-1].date)
    ambiguities = []
    scope = _parse_time_scope(message, trip, days, ambiguities, relative_date_base=None)
    assert scope.day_number == 2
    assert scope.day_date == days[1].date
    assert ambiguities == []
    assert _extract_place_queries(message) == []

    appointment = uuid4()
    entity = _ActivityEntity(appointment, uuid4(), days[2].date, ("西湖",), "sight", time(15), True)
    protected = _resolve_protected_activities(message, [entity], None, ambiguities, trip_start_date=start)
    assert protected == [appointment]
    assert ambiguities == []
    draft = _build_rule_semantic_draft(message, "modify_day", scope)
    assert "add_activity" not in {op.operation for op in draft.operations}


def test_unknown_appointment_and_real_place_still_require_grounding():
    start = date(2026, 10, 16)
    ambiguities = []
    assert _resolve_protected_activities("第3天15点固定活动不要动", [], None, ambiguities,
                                         trip_start_date=start) == []
    assert ambiguities == ["activity_not_found:第3天15点固定活动"]
    assert _extract_place_queries("加入人民公园") == ["人民公园"]
    assert not _is_non_place_reference("步行上限咖啡馆")
    assert _extract_place_queries("加入步行上限咖啡馆") == ["步行上限咖啡馆"]


def test_meta_references_with_positive_verb_do_not_become_places():
    assert _extract_place_queries("把已撤销的步行限制加入规划") == []
    assert _extract_place_queries("把人民公园加入规划") == ["人民公园"]
    assert _extract_place_queries("加入第2天已撤销的步行上限，加入人民公园") == ["人民公园"]
    assert _extract_place_queries("保留其他日期安排不变") == []


def test_revocation_and_relaxation_keep_day_scopes_and_history():
    scope = {"kind": "trip", "trip_id": "trip", "city": "杭州"}
    records = capture_explicit_requirements([], "步行上限30分钟，喜欢拍照", scope=scope,
                                            source_ref="first", force=True)
    records = capture_explicit_requirements(records, "撤销第2天步行上限", scope=scope,
                                            source_ref="second")
    day1 = project_requirements(records, trip_id="trip", city="杭州", day_index=1)
    day2 = project_requirements(records, trip_id="trip", city="杭州", day_index=2)
    assert {(r["key"], r["value"]) for r in day1} == {
        ("max_walking_minutes", 30), ("interest", "photography")}
    assert {(r["key"], r["value"]) for r in day2} == {("interest", "photography")}

    records = capture_explicit_requirements(records, "第2天步行上限放宽到45分钟", scope=scope,
                                            source_ref="third")
    day2 = project_requirements(records, trip_id="trip", city="杭州", day_index=2)
    assert {(r["key"], r["value"]) for r in day2} == {
        ("max_walking_minutes", 45), ("interest", "photography")}
    assert next(r for r in day2 if r["key"] == "max_walking_minutes")["strength"] == "hard"
    unchanged = capture_explicit_requirements(records, "不要把第2天已撤销的步行上限加回来",
                                               scope=scope, source_ref="fourth")
    assert unchanged == records


def test_numeric_historical_limit_cannot_reactivate_revoked_day():
    scope = {'kind': 'trip', 'trip_id': 'trip', 'city': '杭州'}
    records = capture_explicit_requirements([], '步行上限30分钟', scope=scope, source_ref='old')
    records = capture_explicit_requirements(records, '撤销第2天步行上限', scope=scope, source_ref='revoke')
    referenced = capture_explicit_requirements(records, '不要恢复第2天已撤销的步行上限30分钟', scope=scope, source_ref='reference')
    assert referenced == records
    assert project_requirements(referenced, trip_id='trip', city='杭州', day_index=2) == []
    # An affirmative user instruction can restore a requirement; mere reference cannot.
    restored = capture_explicit_requirements(records, '恢复第2天已撤销的步行上限30分钟', scope=scope, source_ref='restore')
    assert [(r['key'], r['value']) for r in project_requirements(restored, trip_id='trip', city='杭州', day_index=2)] == [('max_walking_minutes', 30)]


def test_appointment_reference_checks_minutes_and_preserves_real_ambiguity():
    start = date(2026, 10, 17)
    entity = _ActivityEntity(uuid4(), uuid4(), start, ('预约活动',), 'sight', time(15, 45), True)
    assert _resolve_fixed_activity_reference('第1天15点30分固定活动', [entity], start) == []
    assert _resolve_fixed_activity_reference('第1天15点45分固定活动', [entity], start) == [entity.id]
    second = _ActivityEntity(uuid4(), entity.day_id, start, ('另一预约',), 'sight', time(15, 30), True)
    ambiguities = []
    assert _resolve_protected_activities('第1天15点固定活动不要动', [entity, second], None, ambiguities, trip_start_date=start) == []
    assert ambiguities
