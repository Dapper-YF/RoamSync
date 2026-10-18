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
