from app.assistant_context import ContextEnvelope
from app.read_references import place_catalog, resolve_read_text
from app.read_references import bind_read_task_reference
from app.assistant_capabilities import CapabilityDecision, ReadTask, validate_decision


def comparison():
    return {'user':'比较甲园和乙馆', 'place_cards':[
        {'place':{'place_id':f'00000000-0000-0000-0000-00000000000{i}','name':name,'city':'开封'}}
        for i,name in [(1,'甲园'),(2,'乙馆')]]}


def test_singular_followup_keeps_focus_without_renumbering_comparison():
    history=[comparison(),{'user':'第二个适合了解历史吗？'}]
    catalog=place_catalog(history,ContextEnvelope(browsing_city='开封'))
    assert resolve_read_text('它需要留多久？',catalog)=='乙馆需要留多久？'
    assert resolve_read_text('第一个在哪里？',catalog)=='甲园在哪里？'
    assert resolve_read_text('它们分别是什么？',catalog)=='甲园和乙馆分别是什么？'
    assert '_reference_focus' not in history[0]['place_cards'][0]['place']


def test_two_different_references_do_not_guess_a_singular_focus():
    history=[comparison(),{'user':'第一个和第二个都想看'}]
    catalog=place_catalog(history,ContextEnvelope(browsing_city='开封'))
    assert resolve_read_text('它在哪里',catalog)=='它在哪里'


def test_explicit_peer_and_denied_reference_cannot_donate_wrong_focus():
    history=[comparison(),{'user':'前者和乙馆比较'}]
    catalog=place_catalog(history,ContextEnvelope(browsing_city='开封'))
    assert resolve_read_text('它在哪里',catalog)=='它在哪里'
    history=[comparison(),{'user':'别看前者，介绍乙馆'}]
    catalog=place_catalog(history,ContextEnvelope(browsing_city='开封'))
    assert resolve_read_text('它在哪里',catalog)=='乙馆在哪里'


def test_read_recovery_preserves_other_subjects_and_does_not_invent_capability():
    places=place_catalog([comparison(),{'user':'第二个在哪里'}],ContextEnvelope(browsing_city='开封'))
    for source in ('丙馆比它关门更早吗？','它旁边丙馆几点关门？','如果它今天开放呢？','不要查它的开放时间'):
        task=ReadTask(source_quote=source,names=['甲园'],fact_kind='opening_hours')
        result=bind_read_task_reference(task,places)
        assert result.names==task.names and result.capabilities==[]
    task=ReadTask(source_quote='它今天开放到几点？',origin='甲园',destination='乙馆',fact_kind='opening_hours')
    assert bind_read_task_reference(task,places).capabilities==[]


def test_read_task_uses_server_pronoun_binding_instead_of_wrong_model_name():
    history=[comparison(),{'user':'第二个的地址是什么？'}]
    envelope=ContextEnvelope(browsing_city='开封')
    message='它今天开放到几点？'
    choice=CapabilityDecision(intent='lookup',city='开封',reason_code='current_information',read_tasks=[ReadTask(
        source_quote=message,city='开封',names=['甲园'],query='甲园 开放时间',fact_kind='opening_hours')])
    result=validate_decision(choice,message,history,envelope,[])
    assert result.read_tasks[0].names==['乙馆']
    assert result.read_tasks[0].capabilities==['facts']
    assert not result.read_tasks[0]._clarification
    history=[comparison(),{'user':'介绍前者'},{'user':'介绍乙馆，再说它的地址'}]
    catalog=place_catalog(history,ContextEnvelope(browsing_city='开封'))
    assert resolve_read_text('它在哪里',catalog)=='乙馆在哪里'
