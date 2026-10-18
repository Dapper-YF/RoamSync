"""A small attributed factual slice, never evidence of live venue operations."""
import json
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from .contracts import Place, ReviewedExperience

CATALOG = json.loads(Path(__file__).with_name('reviewed_experiences.json').read_text(encoding='utf-8'))
BY_ID = {item['provider_place_id']: item for item in CATALOG}


def candidate_experience(candidate: dict, city: str) -> dict | None:
    """Bind a formal candidate's provider identity, never its local row UUID."""
    source = candidate.get('source') or {}
    url = urlparse(source.get('url') or '')
    ids = parse_qs(url.query).get('id') or []
    if source.get('provider') not in {'AMap POI', 'amap'} or url.scheme != 'https' or url.hostname != 'www.amap.com' or url.path != '/search' or len(ids) != 1:
        return None
    entry = BY_ID.get(ids[0])
    try:
        approved = (entry and candidate.get('name', candidate.get('display_name')) == entry['name']
            and city.removesuffix('市') == entry['city'].removesuffix('市')
            and abs(float(candidate.get('longitude')) - entry['longitude']) < 0.002
            and abs(float(candidate.get('latitude')) - entry['latitude']) < 0.002)
    except (ValueError, TypeError):
        return None
    return ReviewedExperience.model_validate({key: entry[key] for key in (
        'summary', 'attributes', 'source_url', 'source_title', 'reviewed_at', 'scope', 'unknown'
    )}).model_dump(mode='json') if approved else None


def project_experience(place: Place) -> Place:
    from .provider import stable_place_id
    entry = BY_ID.get(place.ref.external_ref.provider_place_id)
    approved = (entry and place.ref.place_id == stable_place_id(entry['provider_place_id'])
                and place.identity_status == 'provider_identity'
                and place.city == entry['city'] and place.name == entry['name']
                and abs(place.location.longitude - entry['longitude']) < 0.002
                and abs(place.location.latitude - entry['latitude']) < 0.002)
    value = ReviewedExperience.model_validate({key: entry[key] for key in (
        'summary', 'attributes', 'source_url', 'source_title', 'reviewed_at', 'scope', 'unknown'
    )}) if approved else None
    return place.model_copy(update={'experience': value})
