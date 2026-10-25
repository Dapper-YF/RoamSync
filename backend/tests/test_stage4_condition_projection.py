"""A memory update must agree with every existing effective-condition view."""
from app.assistant_context import ContextEnvelope, TaskRequirements, capture_effective_requirements
from app.assistant_memory import MemoryUpdate, apply_memory
from app.requirements import project_requirements


def _active(env):
    return project_requirements(env.requirement_records, topic_id=env.topic_id, city=env.browsing_city)


def test_departed_companion_withdraws_only_its_linked_requirement_and_syncs_count():
    env = ContextEnvelope(topic_id='solo', browsing_city='成都', requirements=TaskRequirements(party_size=2))
    text = '我不喝酒，朋友这次连续步行不能超过15分钟，我这次连续步行不能超过30分钟'
    env = capture_effective_requirements(env, text, message_id='origin')
    env, _, _ = apply_memory(env, [], text, 'origin', [
        MemoryUpdate(field='preferences', operation='add', value='不喝酒', source_quote='我不喝酒'),
        MemoryUpdate(field='requirements', operation='add', value='连续步行不能超过15分钟',
                     source_quote='朋友这次连续步行不能超过15分钟', subject='朋友'),
        MemoryUpdate(field='requirements', operation='add', value='连续步行不能超过30分钟',
                     source_quote='我这次连续步行不能超过30分钟', scope='trip'),
    ])
    departure = '朋友不去了，我一个人去'
    env, _, _ = apply_memory(env, [], departure, 'solo', [
        MemoryUpdate(field='party_size', value='1', source_quote='我一个人去', scope='trip'),
        MemoryUpdate(field='requirements', operation='remove', value='朋友这次连续步行不能超过15分钟',
                     source_quote='朋友不去了', subject='朋友'),
    ])
    assert env.requirements.party_size == 1
    assert [i['value'] for i in env.conversation_memory['preferences']] == ['不喝酒']
    assert [r['text'] for r in _active(env)] == ['我这次连续步行不能超过30分钟']
    assert any(r['status'] == 'revoked' and r['text'].startswith('朋友') for r in env.requirement_records)


def test_unverified_removal_cannot_revoke_a_requirement_record():
    env = ContextEnvelope(topic_id='solo', browsing_city='成都')
    text = '朋友这次连续步行不能超过15分钟'
    env = capture_effective_requirements(env, text, message_id='origin')
    env, _, _ = apply_memory(env, [], '朋友不去了', 'later', [
        MemoryUpdate(field='requirements', operation='remove', value=text, source_quote='朋友不去了', subject='朋友')])
    assert len(_active(env)) == 1
    assert env.conversation_memory['latest_receipt']['updates'][0]['status'] == 'rejected'


def test_same_text_from_other_source_or_global_scope_is_not_revoked():
    from app.requirements import add_requirement
    env = ContextEnvelope(topic_id='solo', browsing_city='成都')
    text = '朋友这次连续步行不能超过15分钟'
    env = capture_effective_requirements(env, text, message_id='origin')
    records = add_requirement(env.requirement_records, text=text, scope={'kind':'global_preference'}, source_ref='unrelated')
    env = env.model_copy(update={'requirement_records':records})
    env, _, _ = apply_memory(env, [], text, 'origin', [
        MemoryUpdate(field='requirements', operation='add', value=text, source_quote=text, subject='朋友')])
    env, _, _ = apply_memory(env, [], '朋友不去了', 'later', [
        MemoryUpdate(field='requirements', operation='remove', value=text, source_quote='朋友不去了', subject='朋友')])
    assert [r['source']['ref'] for r in _active(env)] == ['unrelated']


def test_departure_event_and_solo_projection_do_not_depend_on_optional_model_patch():
    from app.assistant_memory import literal_conditions
    env=ContextEnvelope(topic_id='solo',browsing_city='成都',requirements=TaskRequirements(party_size=2))
    text='朋友这次连续步行不能超过15分钟'
    env=capture_effective_requirements(env,text,message_id='origin')
    env,_,_=apply_memory(env,[],text,'origin',[MemoryUpdate(field='requirements',operation='add',
        value=text,source_quote=text,subject='朋友')])
    text='朋友不去了，我一个人去'
    env,_,_=apply_memory(env,[],text,'solo',literal_conditions(text))
    assert env.requirements.party_size==1 and not _active(env)
    assert not env.conversation_memory['requirements']
    assert all(r['status']=='applied' for r in env.conversation_memory['latest_receipt']['updates'])


def test_hypothetical_or_quoted_departure_keeps_owned_condition():
    from app.assistant_memory import literal_conditions
    env=ContextEnvelope()
    quote='朋友这次连续步行不能超过15分钟'
    env,_,_=apply_memory(env,[],quote,'origin',[MemoryUpdate(field='requirements',value=quote,source_quote=quote,subject='朋友')])
    for text in ['如果朋友不去了，我一个人去','他说“朋友不去了，我一个人去”']:
        result,_,_=apply_memory(env,[],text,'no-authority',literal_conditions(text))
        assert result.conversation_memory['requirements']==env.conversation_memory['requirements']
        assert 'party_size' not in result.conversation_memory['slots']


def test_calendar_day_is_not_duration_but_literal_one_day_candidate_persists():
    from app.assistant_memory import literal_conditions
    text='请先生成成都11月9日的一日候选，10:00到18:00游玩'
    env,_,_=apply_memory(ContextEnvelope(),[],text,'source',literal_conditions(text))
    assert env.conversation_memory['slots']['duration_days']['value']==1
    assert not [u for u in literal_conditions('11月9日出发') if u.field=='duration_days']
