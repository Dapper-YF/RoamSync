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
