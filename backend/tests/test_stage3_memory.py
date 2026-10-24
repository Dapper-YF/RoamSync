from uuid import uuid4
from app.assistant_context import ContextEnvelope
from app.assistant_memory import MemoryUpdate, apply_memory, memory_prompt, condition_ack


def test_self_only_quantity_and_subject_specific_withdrawal():
    env = ContextEnvelope()
    for quote, field, value, subject in [('我不喝酒','preferences','不喝酒',''),
        ('姐姐少走台阶','requirements','姐姐少走台阶','姐姐')]:
        env, _, _ = apply_memory(env, [], quote, uuid4(), [MemoryUpdate(
            field=field, value=value, source_quote=quote, subject=subject)])
    text = '姐姐和外甥都不去了，就我自己去。把只为姐姐设置的少走台阶要求撤掉，我不喝酒这条保留。'
    env, _, changed = apply_memory(env, [], text, uuid4(), [
        MemoryUpdate(field='party_size', value='1', source_quote='就我自己去', scope='trip'),
        MemoryUpdate(field='requirements', operation='remove', value='姐姐少走台阶',
            subject='姐姐', source_quote='姐姐和外甥都不去了')])
    memory = memory_prompt(env)
    assert memory['slots']['party_size']['value'] == 1
    assert not memory['requirements']
    assert memory['preferences'][0]['value'] == '不喝酒'
    assert '1' in condition_ack(env, text, changed)


def test_rejected_update_has_authoritative_receipt_and_no_false_ack():
    env, _, changed = apply_memory(ContextEnvelope(), [], '如果我一个人去呢', uuid4(), [
        MemoryUpdate(field='party_size', value='1', source_quote='我一个人去')])
    receipt = env.conversation_memory['latest_receipt']
    assert receipt['updates'][0]['status'] == 'rejected'
    assert '未应用' in condition_ack(env, '更新人数', changed)
    assert not env.conversation_memory['slots']


def test_invalid_subject_removal_does_not_delete_same_value_user_record():
    env, _, _ = apply_memory(ContextEnvelope(), [], '少走路', uuid4(), [
        MemoryUpdate(field='preferences', value='少走路', source_quote='少走路')])
    env, _, _ = apply_memory(env, [], '撤掉朋友的少走路要求', uuid4(), [
        MemoryUpdate(field='preferences', operation='remove', value='少走路',
            source_quote='撤掉朋友的少走路要求', subject='朋友')])
    assert memory_prompt(env)['preferences'][0]['value'] == '少走路'


def test_subject_clear_preserves_user_and_receipt_matches_final_city_cleanup():
    env = ContextEnvelope(browsing_city='扬州')
    for q, subject, scope in [('我少走路', '', 'personal'), ('姐姐少走台阶', '姐姐', 'trip'), ('扬州看园林', '', 'destination')]:
        env, _, _ = apply_memory(env, [], q, uuid4(), [MemoryUpdate(field='requirements', value=q,
            source_quote=q, subject=subject, scope=scope)])
    env, _, _ = apply_memory(env, [], '取消姐姐的要求', uuid4(), [MemoryUpdate(field='requirements',
        operation='clear', subject='姐姐', source_quote='取消姐姐的要求')])
    assert [r['value'] for r in env.conversation_memory['requirements']] == ['我少走路', '扬州看园林']
    env, _, _ = apply_memory(env, [], '改去南京', uuid4(), [MemoryUpdate(field='city', value='南京', source_quote='改去南京')])
    assert env.conversation_memory['latest_receipt']['effective_requirements'] == env.conversation_memory['requirements']
    assert len(env.conversation_memory['requirements']) == 1
