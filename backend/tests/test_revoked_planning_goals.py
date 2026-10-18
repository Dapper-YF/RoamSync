from app.planning_goals import extract_planning_goals


def goals(text, *, records=None, grounded=None):
    return extract_planning_goals(user_request=text,
        intent_resolution={'grounded_intent': {'constraints': grounded or {}}},
        context={'preferences': {'max_walking_minutes': 30, 'requirement_records': records or []},
                 'days': [{'id': 'day-1', 'date': '2026-10-17'}]})


def test_historical_constraint_does_not_reactivate_grounded_or_stored_limit():
    value = goals('只调整第一天，已撤销的步行不超过30分钟不要恢复，其他日期安排保持不变。',
                  grounded={'max_walking_minutes': 30})
    assert value.hard_goals.max_walking_minutes is None
    assert value.soft_goals.minimize_walking is False


def test_affirmative_replacement_survives_historical_clause():
    value = goals('之前撤销的步行限制不用恢复，但是现在步行最多60分钟，18点前结束。',
                  grounded={'max_walking_minutes': 60})
    assert value.hard_goals.max_walking_minutes == 60
    assert value.hard_goals.end_before == '18:00'


def test_scoped_requirement_history_never_falls_back_to_unscoped_scalar():
    value = goals('请少走路', records=[{'key': 'max_walking_minutes', 'status': 'revoked'}])
    assert value.hard_goals.max_walking_minutes is None
    assert value.soft_goals.minimize_walking


def test_legacy_affirmative_preference_compatibility():
    assert goals('请少走路').hard_goals.max_walking_minutes == 30


def test_do_not_cancel_does_not_revoke_an_affirmative_limit():
    assert goals('不要取消步行30分钟的限制', grounded={'max_walking_minutes': 30}).hard_goals.max_walking_minutes == 30
