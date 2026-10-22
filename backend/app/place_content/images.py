"""Reviewed image projection, independent of provider search and trip rules.

No network calls. Exact external ID plus canonical ID, name, city and coordinate
guards prevent accidental cross-place association. Existing JSON snapshots are
reprojected, so a removed license approval also removes cached image metadata.
"""
import json
from pathlib import Path
from .contracts import Image, Place

MEDIA = Path(__file__).with_name('media')
CATALOG = json.loads(Path(__file__).with_name('reviewed_images.json').read_text(encoding='utf-8'))
BY_ID = {item['provider_place_id']: item for item in CATALOG}
ASSETS = {asset['filename'] for item in CATALOG for photo in item['files'] for asset in photo['assets'].values()}


def reviewed_illustrations(city: str) -> list[dict]:
    """Local reviewed imagery, never a live POI or availability claim."""
    from .provider import normalize_poi

    result = []
    for entry in CATALOG:
        if entry['city'].removesuffix('市') != city.strip().removesuffix('市'):
            continue
        place = normalize_poi({'id': entry['provider_place_id'], 'name': entry['name'],
            'cityname': entry['city'], 'location': f"{entry['longitude']},{entry['latitude']}",
            'typecode': '110000'})
        if place.images:
            result.append({'ref': place.ref, 'name': place.name, 'city': place.city,
                'location': place.location, 'images': place.images})
    return result


def project_images(place: Place) -> Place:
    from .provider import stable_place_id

    entry = BY_ID.get(place.ref.external_ref.provider_place_id)
    approved = []
    if (entry and place.identity_status in {'provider_identity', 'provider_unavailable'}
        and place.ref.place_id == stable_place_id(entry['provider_place_id'])
        and place.name == entry['name'] and place.city == entry['city']
        and abs(place.location.longitude - entry['longitude']) < 0.002
        and abs(place.location.latitude - entry['latitude']) < 0.002):
        for photo in entry['files']:
            if not all((MEDIA / asset['filename']).is_file() for asset in photo['assets'].values()):
                continue
            approved.append(Image(
                url='/api/v1/media/place-images/' + photo['assets']['960']['filename'],
                thumbnail_url='/api/v1/media/place-images/' + photo['assets']['480']['filename'],
                place_ref=place.ref, provider='wikimedia_commons', title=photo['caption'],
                attribution=photo['author'], source_url=photo['source_url'],
                usage_basis='reviewed_commons_license', license_name=photo['license'],
                license_url=photo['license_url'], changes=photo['changes'], reviewed_at=photo['reviewed_at'],
            ))
    status = 'available' if approved else ('withheld_pending_license' if place.image_status in {'available', 'withheld_pending_license'} else 'missing')
    from .experiences import project_experience
    return project_experience(place.model_copy(update={'images': approved, 'image_status': status}))
