from app.place_content.experiences import CATALOG, project_experience, candidate_experience
from app.place_content.provider import normalize_poi, stable_place_id


def test_reviewed_experience_is_exact_and_explicit_about_unknown_operations():
    for entry in CATALOG:
        place = normalize_poi({'id': entry['provider_place_id'], 'name': entry['name'],
            'cityname': entry['city'], 'location': f"{entry['longitude']},{entry['latitude']}", 'typecode': '110000'})
        assert place.experience.summary and place.experience.unknown
        assert place.experience.usage_basis == 'original_factual_summary_with_attribution'
        for altered in [place.model_copy(update={'name': place.name + '分馆'}),
            place.model_copy(update={'city': '苏州市'}),
            place.model_copy(update={'identity_status': 'provider_id_invalid'}),
            place.model_copy(update={'ref': place.ref.model_copy(update={'place_id': stable_place_id('OTHER')})}),
            place.model_copy(update={'location': place.location.model_copy(update={'longitude': 0})})]:
            assert project_experience(altered).experience is None


def test_removed_review_reprojects_cached_content(monkeypatch):
    import app.place_content.experiences as module
    entry = CATALOG[0]
    saved = normalize_poi({'id': entry['provider_place_id'], 'name': entry['name'], 'cityname': entry['city'],
                          'location': f"{entry['longitude']},{entry['latitude']}"})
    assert saved.experience
    monkeypatch.setattr(module, 'BY_ID', {})
    assert project_experience(saved).experience is None


def test_formal_candidate_content_uses_provider_identity_not_local_row_id():
    entry = CATALOG[1]
    candidate = {'id': 'unrelated-local-row-id', 'name': entry['name'],
        'longitude': entry['longitude'], 'latitude': entry['latitude'],
        'source': {'provider': 'AMap POI', 'url': 'https://www.amap.com/search?id=' + entry['provider_place_id']}}
    assert candidate_experience(candidate, '杭州')['attributes']
    assert candidate_experience(candidate, '南京') is None
    assert candidate_experience(candidate | {'source': {'provider': 'user_note', 'url': candidate['source']['url']}}, '杭州') is None
    assert candidate_experience(candidate | {'name': entry['name'] + '分馆'}, '杭州') is None
