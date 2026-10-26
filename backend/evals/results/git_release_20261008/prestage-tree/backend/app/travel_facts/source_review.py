"""Offline triage and reviewed promotion policy. Never writes production state."""
from collections import Counter
from datetime import date, datetime, timedelta, UTC
from urllib.parse import urlparse

from .official_collector import PROFILES, digest, normalize, accepted_payload
from .opening_hours import plain, reviewed_schedule
import re


POLICY = 'official-review-promotion-v1'


def triage(collection, *, target_date):
    """Reduce inspection effort without accepting or excluding historical truth."""
    target = date.fromisoformat(target_date)
    rows = []
    for candidate in collection.candidates:
        text = candidate['title'] + ' ' + plain(candidate['body'])
        categories = []
        if candidate['review_reason'] in {'not_operational_schedule', 'duplicate_content'}:
            categories.append('obviously_irrelevant')
        else:
            categories.append('likely_operational')
        if candidate['branch_scope'] in {'ambiguous', 'subvenue', 'other_venue', '孤山馆区'}:
            categories.append('venue_scope_ambiguous')
        ranges = candidate['date_scope']['effective_ranges']
        if not ranges:
            categories.append('effective_date_ambiguous')
        # Publication age is a triage hint, never evidence of expiry.
        if date.fromisoformat(candidate['publication'][:10]).year < target.year:
            categories.append('historical')
        if re.search(r'修订|更正|替代|调整为', text):
            categories.append('possible_supersession')
        if re.search(r'临时闭馆|暂停开放|暂停开馆|维修|闭院', text):
            categories.append('temporary_closure')
        rows.append({'notice_id': candidate['notice_id'], 'content_hash': candidate['content_hash'],
                     'categories': categories, 'review_status': candidate['review_status'],
                     'human_review_priority': 'high' if any(x in categories for x in
                         ('temporary_closure', 'possible_supersession')) else
                         'low' if 'obviously_irrelevant' in categories else 'normal',
                     'auto_accepted': False, 'auto_out_of_scope': False})
    for error in collection.errors:
        if error.startswith('notice:'):
            rows.append({'notice_id': error.split(':')[1], 'categories': ['schema_broken'],
                         'error': error, 'human_review_priority': 'high',
                         'auto_accepted': False, 'auto_out_of_scope': False})
    return {'policy': POLICY, 'target_date': target_date, 'source_id': collection.source_id,
            'counts': dict(Counter(c for row in rows for c in row['categories'])), 'items': rows,
            'accepted_truth_changed': False, 'historical_is_not_expiry': True}


def validate_registry(registry, profiles):
    """Reject ambiguous/malformed review versions, rather than last-write-wins."""
    if registry.get('policy') != POLICY or type(registry.get('version')) is not int or registry['version'] < 1:
        raise ValueError('registry version/policy required')
    if registry['version'] > 1 and not re.fullmatch(r'[0-9a-f]{64}', registry.get('previous_registry_hash', '')):
        raise ValueError('review revision must name previous registry hash')
    if not isinstance(registry.get('entries'), list):
        raise ValueError('registry entries must be list')
    seen = set()
    for review in registry['entries']:
        key = (review['source_id'], review['notice_id'])
        if key in seen:
            raise ValueError('duplicate review identity; explicit replacement required')
        seen.add(key)
        profile = profiles[review['source_id']]
        if review['canonical_venue_ref'] != profile.venue_ref or review['schema_version'] != profile.schema_version:
            raise ValueError('review venue/schema mismatch')
        for field in ('content_hash', 'html_fingerprint'):
            if not re.fullmatch(r'[0-9a-f]{64}', review[field]):
                raise ValueError('invalid review fingerprint')
        if review['review_status'] not in {'accepted', 'rejected'} or not review['reviewer'].strip() or not review['reason'].strip():
            raise ValueError('explicit review required')
        datetime.fromisoformat(review['reviewed_at'])
        if review['review_status'] == 'accepted' and (review['branch_scope'] != profile.branch or not review['effective_ranges']):
            raise ValueError('accepted review requires exact venue and effective range')
        for first, last in review['effective_ranges']:
            if date.fromisoformat(first) > date.fromisoformat(last):
                raise ValueError('reversed effective range')
    return digest(registry)


def revise_registry(previous, replacement, profiles, *, expected_hash):
    """Explicit optimistic revision, returning a new artifact; no file overwrite."""
    if validate_registry(previous, profiles) != expected_hash:
        raise ValueError('registry changed; re-review current version')
    key = (replacement['source_id'], replacement['notice_id'])
    entries = [r for r in previous['entries'] if (r['source_id'], r['notice_id']) != key]
    revised = {'policy': POLICY, 'version': previous['version'] + 1,
               'previous_registry_hash': expected_hash, 'entries': entries + [replacement]}
    validate_registry(revised, profiles)
    return revised


def promotion_gate(profile, collection, candidate, *, target_date, now, registry):
    """Date-specific decision. Accepted alone is insufficient to be promotable.

    This is an offline eligibility decision, never promotion/deployment itself.
    Every nonduplicate listing entry must have a valid explicit review to prove
    exception coverage; keyword triage cannot certify absence of exceptions.
    """
    target = date.fromisoformat(target_date)
    reasons = []
    try:
        registry_hash = validate_registry(registry, PROFILES | {profile.source_id: profile})
    except (ValueError, KeyError, TypeError):
        registry_hash = None
        reasons.append('registry_invalid')
    if collection.source_id != profile.source_id or collection.venue_ref != profile.venue_ref:
        reasons.append('collection_scope_mismatch')
    if collection.schema_status != 'valid':
        reasons.append('schema_invalid')
    if collection.collection_status != 'complete' or not collection.pagination_complete or collection.errors:
        reasons.append('collection_incomplete')
    try:
        fetched = datetime.fromisoformat(collection.fetched_at)
        if fetched.tzinfo is None or now.tzinfo is None or not timedelta(0) <= now - fetched <= timedelta(minutes=30):
            reasons.append('collection_not_fresh')
    except (TypeError, ValueError):
        reasons.append('collection_not_fresh')
    entries = {(r['source_id'], r['notice_id']): r for r in registry.get('entries', [])} if registry_hash else {}
    reviewed_scan = bool(collection.exception_scan_complete and not collection.review_required)
    for item in collection.candidates:
        if item.get('duplicate_of'):
            continue
        review = entries.get((profile.source_id, item['notice_id']))
        if not review or review['content_hash'] != item['content_hash'] or review['html_fingerprint'] != item['html_fingerprint']:
            reviewed_scan = False
        elif (item['review_status'] not in {'accepted', 'rejected', 'superseded'} or
              review['canonical_venue_ref'] != item['canonical_venue_ref'] or
              review['branch_scope'] != item['branch_scope'] or
              review['effective_ranges'] != item['date_scope']['effective_ranges'] or
              (item['review_status'] != 'superseded' and review['review_status'] != item['review_status'])):
            reviewed_scan = False
    if not reviewed_scan:
        reasons.append('exception_review_incomplete')
    if candidate not in collection.accepted_snapshots or candidate['review_status'] != 'accepted':
        reasons.append('not_accepted_snapshot')
    if candidate['branch_scope'] != profile.branch or candidate['canonical_venue_ref'] != profile.venue_ref:
        reasons.append('venue_scope_unresolved')
    if (urlparse(candidate['source_api']).hostname != profile.domain or candidate['source_api'] != profile.endpoint or
            urlparse(candidate['source_url']).scheme != 'https' or urlparse(candidate['source_url']).hostname != profile.domain):
        reasons.append('source_not_official')
    ranges = candidate['date_scope']['effective_ranges']
    if not any(date.fromisoformat(first) <= target <= date.fromisoformat(last) for first, last in ranges):
        reasons.append('effective_range_unresolved')
    schedule = None
    try:
        current = normalize(profile, candidate['raw_notice'])
        if current['content_hash'] != candidate['content_hash'] or current['html_fingerprint'] != candidate['html_fingerprint']:
            raise ValueError('snapshot changed')
        schedule = reviewed_schedule(profile.source_id, accepted_payload(profile, candidate), target)
    except (ValueError, KeyError, TypeError):
        reasons.append('content_not_frozen')
    if schedule is None:
        reasons.append('parser_source_not_understood')
    # Compare interpretable date-specific values across all accepted authorities.
    signatures = set()
    for other in collection.accepted_snapshots:
        if not any(date.fromisoformat(a) <= target <= date.fromisoformat(b) for a, b in other['date_scope']['effective_ranges']):
            continue
        try:
            parsed = reviewed_schedule(profile.source_id, accepted_payload(profile, other), target)
        except (ValueError, KeyError, TypeError):
            parsed = None
        if parsed is None:
            reasons.append('overlapping_source_not_understood')
        else:
            signatures.add(digest({k: parsed.get(k) for k in ('closed', 'open', 'close', 'admission')}))
    if len(signatures) > 1:
        reasons.append('unresolved_source_conflict')
    return {'policy': POLICY, 'notice_id': candidate['notice_id'], 'target_date': target_date,
            'promotable': not reasons, 'blockers': sorted(set(reasons)), 'registry_hash': registry_hash,
            'content_hash': candidate['content_hash'], 'collection_hash': digest(collection.__dict__),
            'evaluated_at': now.astimezone(UTC).isoformat(), 'production_promoted': False,
            'semantics': 'date_specific_official_notice_only', 'regular_exception_readiness': 'NOT READY'}
