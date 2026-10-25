"""Pure contract probes; run from isolated backend with its directory on PYTHONPATH."""
import json
from app.assistant_capabilities import CapabilityDecision, ReadTask, validate_decision
from app.assistant_context import ContextEnvelope
from app.read_references import explanation_requested


def probe(message, tasks, expected_poi):
    decision = CapabilityDecision(intent='lookup', capabilities=['web'],
        reason_code='stable_knowledge', read_tasks=[ReadTask(**task) for task in tasks])
    signatures = []
    for _ in range(3):
        decision = validate_decision(decision, message, [], ContextEnvelope())
        signature = [(tuple(t.capabilities), t.city, tuple(t.names), t.source_quote,
            t._clarification, t._identity_only) for t in decision.read_tasks]
        signatures.append(signature)
        actual = {(t.city, name) for t in decision.read_tasks if 'poi' in t.capabilities
            and not t._clarification for name in t.names}
        assert actual == expected_poi, (actual, expected_poi, signature)
        assert len(decision.read_tasks) <= 5
        assert not any((decision.candidate_command, decision.planning_draft,
            decision.authorization_quote, decision.creation, decision.saved_intentions))
    assert signatures[0] == signatures[1] == signatures[2], signatures


CASES = [
    ('denied_address', '介绍苏州拙政园，拙政园地址不要查，只给狮子林照片', [
        dict(source_quote='介绍苏州拙政园，拙政园地址不要查', capabilities=[], city='苏州', names=['拙政园']),
        dict(source_quote='只给狮子林照片', capabilities=['web'], city='苏州', names=['狮子林'])],
        {('苏州', '狮子林')}),
    ('explicit_photo_target', '比较苏州拙政园和狮子林，只给狮子林配图', [
        dict(source_quote='比较苏州拙政园和狮子林', capabilities=['web'], city='苏州', names=['拙政园', '狮子林']),
        dict(source_quote='只给狮子林配图', capabilities=['web'], city='苏州', names=['狮子林'])],
        {('苏州', '狮子林')}),
    ('city_identity', '查上海中山公园地址，给我看北京中山公园照片', [
        dict(source_quote='查上海中山公园地址', capabilities=['poi'], city='上海', names=['中山公园']),
        dict(source_quote='给我看北京中山公园照片', capabilities=['web'], city='北京', names=['中山公园'])],
        {('上海', '中山公园'), ('北京', '中山公园')}),
    ('bad_source', '只给苏州狮子林照片', [
        dict(source_quote='只给苏州狮子林照片', capabilities=['web'], city='苏州', names=['拙政园'])], set()),
]

if __name__ == '__main__':
    results = []
    for name, message, tasks, expected in CASES:
        try:
            probe(message, tasks, expected)
            results.append({'name': name, 'passed': True})
        except AssertionError as error:
            results.append({'name': name, 'passed': False, 'detail': str(error)})
    for message in ['不用解释拙政园有什么值得看', '不想知道拙政园有什么值得看']:
        results.append({'name': message, 'passed': not explanation_requested(message)})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    raise SystemExit(0 if all(result['passed'] for result in results) else 1)
