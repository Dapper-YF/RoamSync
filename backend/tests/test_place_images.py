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


def test_destination_catalog_is_local_city_scoped_and_reuses_approved_assets(monkeypatch):
    app = FastAPI()
    app.include_router(create_router(None))  # No search service or network required.
    client = TestClient(app)
    response = client.get('/api/v1/media/place-images', params={'city': '成都'})
    assert response.status_code == 200
    by_name = {item['name']: item for item in response.json()['items']}
    assert set(by_name) == {'人民公园', '宽窄巷子景区'}
    item = by_name['人民公园']
    assert item['name'] == '人民公园' and item['city'] == '成都市'
    assert item['ref']['place_id'] == str(stable_place_id('B001C7X8QA'))
    assert item['images'][0]['usage_basis'] == 'reviewed_commons_license'
    assert client.get(item['images'][0]['url']).content.startswith(b'\xff\xd8')
    assert client.get('/api/v1/media/place-images', params={'city': '没有照片的城市'}).json() == {'items': []}
    assert client.get('/api/v1/media/place-images').status_code == 422
    import app.place_content.images as images
    monkeypatch.setattr(images, 'MEDIA', MEDIA / 'missing')
    assert client.get('/api/v1/media/place-images', params={'city': '成都市'}).json() == {'items': []}


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


def test_kuanzhai_cc0_photo_binds_only_the_exact_whole_scenic_area():
    entries = [row for row in CATALOG if row['provider_place_id'] == 'B001C7YCM4']
    assert len(entries) == 1
    entry = entries[0]
    assert (entry['name'], entry['city'], entry['longitude'], entry['latitude']) == ('宽窄巷子景区', '成都市', 104.053307, 30.663869)
    place = normalize_poi({'id': 'B001C7YCM4', 'name': entry['name'], 'cityname': entry['city'],
        'location': '104.053307,30.663869', 'typecode': '110000'})
    assert str(place.ref.place_id) == '8ca144f2-f437-5d2e-a38a-9b77c7363e0b'
    photo, = place.images
    assert photo.attribution == 'Daderot' and photo.license_name == 'CC0'
    assert photo.license_url == 'https://creativecommons.org/publicdomain/zero/1.0/deed.en'
    assert photo.place_ref == place.ref
    assert photo.source_url.endswith('File:Street_scene_-_Kuanzhai_Alleys_-_Chengdu,_China_-_DSC05311.jpg')
    assert entry['files'][0]['original_sha1'] == 'd85ed6d21e60ae8040959da487974b4b68bf65fa'
    # Nearby metro, shops, individual scenic sub-sites and entrances cannot borrow this photo.
    for provider_id, name, typecode in [('BV10536811', '宽窄巷子(地铁站)', '150500'),
        ('B0FFIL06X6', '宽巷子3号(宽窄巷子店)', '050000'),
        ('B0FFHQRM8G', '宽窄巷子景区-窄径', '110000'),
        ('B0FFHXLNMY', '宽窄巷子(B口)', '050000')]:
        assert not normalize_poi({'id': provider_id, 'name': name, 'cityname': entry['city'],
            'location': '104.053307,30.663869', 'typecode': typecode}).images
    app = FastAPI()
    app.include_router(create_router(None))
    with TestClient(app) as client:
        for size, url in [('480', photo.thumbnail_url), ('960', photo.url)]:
            response = client.get(url)
            asset = entry['files'][0]['assets'][size]
            assert response.status_code == 200 and response.headers['content-type'] == 'image/jpeg'
            assert len(response.content) == asset['bytes']
            assert hashlib.sha256(response.content).hexdigest() == asset['sha256']


def test_all_reviewed_local_variants_match_the_license_manifest_digests():
    for entry in CATALOG:
        assert entry['identity_evidence'] and entry['provider_place_id']
        for photo in entry['files']:
            assert photo['author'] and photo['reviewed_at'] and photo['changes']
            assert photo['source_url'].startswith('https://commons.wikimedia.org/wiki/File:')
            assert photo['license_url'].startswith('https://creativecommons.org/')
            assert len(photo['original_sha1']) == 40
            for asset in photo['assets'].values():
                blob = (MEDIA / asset['filename']).read_bytes()
                assert blob.startswith(b'\xff\xd8')
                assert len(blob) == asset['bytes']
                assert hashlib.sha256(blob).hexdigest() == asset['sha256']
