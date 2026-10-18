from datetime import date, time
from types import SimpleNamespace
from uuid import uuid4

from app.openai_planner import preserve_out_of_scope_activities
from app.planning_intent_service import _ActivityEntity, _ground_semantic_intent
from app.schemas import CandidatePlanSnapshot, SemanticIntentDraft, SemanticIntentOperation


def test_protection_on_other_day_never_expands_planner_mutation_scope():
    target, protected_day = uuid4(), uuid4()
    protected, other = uuid4(), uuid4()
    entity = _ActivityEntity(protected, protected_day, date(2026, 10, 19), ('固定活动',), 'culture', time(15), True)
    grounded = _ground_semantic_intent(
        SemanticIntentDraft(primary_intent='replan_trip', operations=[SemanticIntentOperation(operation='replan_trip', raw_text='只调整第二天，第三天固定活动不要动')], confidence=1, parser_version='fixture'),
        trip_id=uuid4(), target_day=SimpleNamespace(id=target), selected_activity_id=None,
        protected_activity_ids=[protected], entities=[entity], candidates=[], inherited_missing_fields=[], inherited_ambiguities=[])
    assert grounded.target_day_ids == [target]
    assert grounded.target_activity_ids == []
    activity = {'id': str(other), 'place_id': str(uuid4()), 'display_name': '第三天其他活动',
                'scheduled_time': '17:00', 'duration_minutes': 45, 'estimated_cost_fen': 0,
                'schedule_locked': False, 'status': 'planned', 'source': {'id': str(uuid4())}}
    state = {'intent_resolution': {'grounded_intent': grounded.model_dump(mode='json')},
             'planning_context': {'days': [{'id': str(target), 'date': '2026-10-18', 'activities': [], 'route_mode': 'walk'},
                {'id': str(protected_day), 'date': '2026-10-19', 'activities': [activity], 'route_mode': 'walk'}]}}
    preserved = preserve_out_of_scope_activities(CandidatePlanSnapshot(activities=[]), state)
    assert len(preserved.activities) == 1
    assert str(preserved.activities[0].replaces_activity_id) == str(other)
    assert preserved.activities[0].planned_start_time == time(17)
    assert preserved.activities[0].duration_minutes == 45
