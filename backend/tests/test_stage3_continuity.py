from app.assistant_context import ContextEnvelope
from app.companion_state import ConversationState, resolve_suggestions
from app.read_references import place_catalog, resolve_read_text, read_reference_context, task_referents
from app.assistant_capabilities import CapabilityDecision, ReadTask, validate_decision


def test_named_plural_comparison_is_not_an_absent_suggestion():
    _, gaps = resolve_suggestions('比较福州三坊七巷和上下杭，它们分别适合看什么', ConversationState())
    assert not gaps


def test_route_result_order_does_not_reorder_comparison():
    ps = [{'place_id': '00000000-0000-0000-0000-00000000000'+str(i),
        'name': n, 'city': '扬州'} for i, n in enumerate(['个园', '何园'], 1)]
    history = [{'user': '比较个园和何园', 'place_cards': [{'place': p} for p in ps]},
        {'user': '从第二个到第一个步行', 'place_cards': [{'place': p} for p in reversed(ps)]}]
    catalog = place_catalog(history, ContextEnvelope(browsing_city='扬州'))
    assert resolve_read_text('第一个', catalog) == '个园'
    assert resolve_read_text('它们的位置', catalog) == '个园和何园的位置'


def test_explicit_read_tasks_survive_redundant_direct_label():
    text = '查扬州个园的位置，只是咨询不要创建安排'
    d = CapabilityDecision(intent='direct', reason_code='stable_knowledge', read_tasks=[
        ReadTask(source_quote='查扬州个园的位置', capabilities=['poi'], city='扬州', names=['个园'])])
    validated = validate_decision(d, text, [], ContextEnvelope())
    assert validated.intent == 'lookup' and len(validated.read_tasks) == 1


def test_same_turn_plural_names_share_parent_city_without_identity_fabrication():
    text = '比较扬州个园和何园，并查它们的位置'
    d = CapabilityDecision(intent='direct', reason_code='stable_knowledge', read_tasks=[
        ReadTask(source_quote='查它们的位置', capabilities=['poi'], city='扬州', names=[n]) for n in ['个园', '何园']])
    validated = validate_decision(d, text, [], ContextEnvelope())
    assert validated.intent == 'lookup'
    refs = task_referents(text, validated, [])
    assert resolve_read_text('它们', refs) == '个园和何园'
    assert all(p['place_id'] is None for p in refs)
    assert not read_reference_context('个园和第三个比较', refs)['owns_reference']


def test_named_reverse_route_preserves_original_order():
    ps = [{'place_id': '00000000-0000-0000-0000-00000000000'+str(i),
        'name': n, 'city': '扬州'} for i, n in enumerate(['个园', '何园'], 1)]
    history = [{'user': '比较个园和何园', 'place_cards': [{'place': p} for p in ps]},
        {'user': '从何园到个园查步行路线', 'place_cards': [{'place': p} for p in reversed(ps)]}]
    assert resolve_read_text('第一个', place_catalog(history, ContextEnvelope(browsing_city='扬州'))) == '个园'
