import hashlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.place_content.images import CATALOG, MEDIA, project_images
from app.place_content.provider import normalize_poi, stable_place_id
from app.place_content.routes import create_router


def reviewed_place():
    row = CATALOG[0]
    return normalize_poi({'id': row['provider_place_id'], 'name': row['name'], 'cityname': row['city'],
        'location': f"{row['longitude']},{row['latitude']}", 'typecode': '110000',
        'photos': [{'url': 'https://restricted.example/not-used.jpg'}]})


def test_exact_identity_and_license_are_required_not_just_name():
    place = reviewed_place()
    assert place.images and place.image_status == 'available'
    for photo in place.images:
        assert photo.place_ref == place.ref
        assert photo.provider == 'wikimedia_commons'
        assert photo.license_url.startswith('https://creativecommons.org/')
        assert photo.attribution and photo.reviewed_at and photo.changes
    for altered in [place.model_copy(update={'name':'人民公园-雕塑'}),
        place.model_copy(update={'city':'苏州市'}),
        place.model_copy(update={'ref':place.ref.model_copy(update={'place_id': stable_place_id('OTHER')})}),
        place.model_copy(update={'location':place.location.model_copy(update={'longitude':120})}),
        place.model_copy(update={'identity_status':'provider_id_invalid'})]:
        assert project_images(altered).images == []
    # Same canonical name with a different provider ID cannot borrow the photo.
    assert not normalize_poi({'id':'ANOTHER_PARK', 'name':place.name,'cityname':place.city,
        'location':'104.057641,30.65699','typecode':'110000'}).images


def test_approval_removal_reprojects_saved_metadata(monkeypatch):
    import app.place_content.images as images
    saved = reviewed_place()
    monkeypatch.setattr(images, 'BY_ID', {})
    assert project_images(saved).images == []


def test_missing_asset_does_not_break_place(monkeypatch):
    import app.place_content.images as images
    monkeypatch.setattr(images, 'MEDIA', MEDIA / 'missing')
    place = reviewed_place()
    assert not place.images and place.name


def test_media_allowlist_and_no_open_proxy():
    app = FastAPI()
    app.include_router(create_router(None))
    client = TestClient(app)
    filename = CATALOG[0]['files'][0]['assets']['480']['filename']
    response = client.get('/api/v1/media/place-images/' + filename)
    assert response.status_code == 200 and response.headers['content-type'] == 'image/jpeg'
    assert response.content.startswith(b'\xff\xd8')
    for name in ['unknown.jpg', 'https:evil.jpg', 'reviewed_images.json']:
        assert client.get('/api/v1/media/place-images/' + name).status_code == 404


def test_new_hangzhou_image_bindings_and_local_asset_http_projection():
    expected = {
        "B023B13L9M": ("杭州西湖风景名胜区", 120.121358, 30.222692),
        "B023B09JLL": ("中国丝绸博物馆", 120.151292, 30.22287),
        "B0FFFWQGI8": ("杭州博物馆", 120.166525, 30.239091),
    }
    selected = [entry for entry in CATALOG if entry["provider_place_id"] in expected]
    assert {entry["provider_place_id"] for entry in selected} == set(expected)

    app = FastAPI()
    app.include_router(create_router(None))
    with TestClient(app) as client:
        for entry in selected:
            name, longitude, latitude = expected[entry["provider_place_id"]]
            assert (entry["name"], entry["city"], entry["longitude"], entry["latitude"]) == (name, "杭州市", longitude, latitude)
            assert len(entry["files"]) == 1
            place = normalize_poi({"id": entry["provider_place_id"], "name": name, "cityname": "杭州市",
                "location": f"{longitude},{latitude}", "typecode": "110000"})
            assert place.ref.place_id == stable_place_id(entry["provider_place_id"])
            assert place.image_status == "available" and len(place.images) == 1
            photo = place.images[0]
            assert photo.place_ref == place.ref
            assert photo.provider == "wikimedia_commons" and photo.license_name == "CC BY-SA 4.0"
            assert photo.source_url.startswith("https://commons.wikimedia.org/wiki/File:")
            assert photo.attribution and photo.license_url == "https://creativecommons.org/licenses/by-sa/4.0"
            for size, url in (("480", photo.thumbnail_url), ("960", photo.url)):
                response = client.get(url)
                assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
                assert response.content.startswith(b"\xff\xd8")
                assert hashlib.sha256(response.content).hexdigest() == entry["files"][0]["assets"][size]["sha256"]
