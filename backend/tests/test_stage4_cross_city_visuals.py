from app.assistant_context import ContextEnvelope
from app.assistant_images import subjects_for_answer
from app.requirement_language import is_context_only_statement


def test_explicit_photos_are_independent_of_negated_planning_and_aggregation():
    bundle = {'assistant': '拙政园看水，狮子林看假山。', 'place_cards': [
        {'place': {'name': '拙政园'}}, {'place': {'name': '狮子林'}}]}
    assert [s['subject'] for s in subjects_for_answer(bundle,
        '比较拙政园和狮子林，给我看看对应地点的实景照片。先聊聊，不安排也不保存。', ContextEnvelope())] == ['拙政园', '狮子林']


def test_workflow_adverbs_do_not_create_travel_constraints():
    for text in ['仍然先不要保存', '暂且不采用', '依然只展示候选', '暂时不要保存']:
        assert is_context_only_statement(text)
    for text in ['仍然不要吃辣', '暂且不要安排爬山', '仍然先不要保存路线截图到相册']:
        assert not is_context_only_statement(text)


def test_generation_or_storage_limits_do_not_cancel_real_photo_reads():
    from app.assistant_images import image_requested
    bundle = {'assistant': '拙政园看水。', 'place_cards': [{'place': {'name': '拙政园'}}]}
    for text in ['不要生成图片，我要拙政园实景照片', '给我看看拙政园照片，不要保存图片']:
        assert image_requested(text)
        assert [s['subject'] for s in subjects_for_answer(bundle, text, ContextEnvelope())] == ['拙政园']
    assert not image_requested('不要图片')


def test_photo_target_scope_does_not_expand_to_every_compared_place():
    bundle = {'assistant': '拙政园看水，狮子林看假山。', 'place_cards': [
        {'place': {'name': '拙政园'}}, {'place': {'name': '狮子林'}}]}
    for text in ['比较拙政园和狮子林，只给狮子林配图', '给我看狮子林照片，不要拙政园照片',
        '给我看狮子林的照片，不要拙政园的照片']:
        assert [s['subject'] for s in subjects_for_answer(bundle, text, ContextEnvelope())] == ['狮子林']


def test_retrieval_does_not_consume_comparison_or_visual_identity_goals():
    from app.assistant_capabilities import CapabilityDecision, ReadTask, validate_decision
    text = '我想去苏州看园林，先比较拙政园（东北街178号）和狮子林（园林路23号），各有什么值得看？请展示两个地方的实景参考图片，先不要生成或保存行程。'
    comparison = '先比较拙政园（东北街178号）和狮子林（园林路23号），各有什么值得看'
    decision = CapabilityDecision(intent='direct', capabilities=['web'], city='苏州',
        reason_code='stable_knowledge', illustrate=True, read_tasks=[
            ReadTask(source_quote=comparison, capabilities=['web'], city='苏州', names=['拙政园','狮子林']),
            ReadTask(source_quote='请展示两个地方的实景参考图片', capabilities=['web'], city='苏州', names=['拙政园','狮子林'])])
    for _ in range(2):
        decision = validate_decision(decision, text, [], ContextEnvelope(browsing_city='苏州'))
        assert any(not t.capabilities and t.names == ['拙政园','狮子林'] for t in decision.read_tasks)
        assert any('poi' in t.capabilities and t.names == ['拙政园','狮子林'] for t in decision.read_tasks)
        assert len(decision.read_tasks) <= 5


def test_visual_goal_cannot_restore_denied_lookup_or_a_nonrequested_peer():
    from app.assistant_capabilities import CapabilityDecision, ReadTask, validate_decision
    text = '介绍苏州拙政园，拙政园地址不要查，只给狮子林照片'
    decision = CapabilityDecision(intent='lookup', reason_code='stable_knowledge', read_tasks=[
        ReadTask(source_quote='介绍苏州拙政园，拙政园地址不要查', names=['拙政园'], city='苏州'),
        ReadTask(source_quote='只给狮子林照片', names=['狮子林'], city='苏州', capabilities=['web'])])
    for _ in range(2):
        decision = validate_decision(decision, text, [], ContextEnvelope(browsing_city='苏州'))
        assert not any('poi' in t.capabilities and '拙政园' in t.names and not t._clarification for t in decision.read_tasks)
        assert sum('poi' in t.capabilities and '狮子林' in t.names and not t._clarification for t in decision.read_tasks) == 1


def test_visual_identity_deduplication_respects_each_task_city():
    from app.assistant_capabilities import CapabilityDecision, ReadTask, validate_decision
    text = '查上海中山公园地址，再看北京中山公园照片'
    decision = CapabilityDecision(intent='lookup', reason_code='place_identity', read_tasks=[
        ReadTask(source_quote='查上海中山公园地址', city='上海', names=['中山公园'], capabilities=['poi']),
        ReadTask(source_quote='再看北京中山公园照片', city='北京', names=['中山公园'], capabilities=['web'])])
    for _ in range(2):
        decision = validate_decision(decision, text, [], ContextEnvelope())
        assert {t.city for t in decision.read_tasks if 'poi' in t.capabilities and not t._clarification} == {'上海','北京'}


def test_negated_explanations_do_not_become_new_completion_goals():
    from app.read_references import explanation_requested
    for text in ['不用解释拙政园有什么值得看', '不想知道拙政园有什么值得看',
        '拙政园有什么值得看先不要讲']:
        assert not explanation_requested(text)
    assert explanation_requested('拙政园各有什么值得看')
