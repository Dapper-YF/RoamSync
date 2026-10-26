"""Bounded source-repair acceptance and versioned review registry CLI. Offline only."""
import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import datetime, UTC
from pathlib import Path

from app.travel_facts.official_collector import PROFILES, collect
from app.travel_facts.source_review import POLICY, triage, promotion_gate, validate_registry, revise_registry
from evals.opening_collector import inherited_reviews
from evals.phase25_final import snapshot


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents a review/evaluation from erasing its baseline.
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


async def run(output, target_date, registry):
    validate_registry(registry, PROFILES)
    write_new(output / 'review_registry.json', registry)
    baseline = snapshot()
    sources = []
    for source, profile in PROFILES.items():
        result = await collect(profile, reviews=registry['entries'],
                               progress=lambda p: print(source, p['page'], p['items'], flush=True))
        write_new(output / f'{source}_collection.json', asdict(result))
        triaged = triage(result, target_date=target_date)
        write_new(output / f'{source}_triage.json', triaged)
        decisions = [promotion_gate(profile, result, c, target_date=target_date,
                                     now=datetime.now(UTC), registry=registry)
                     for c in result.candidates if c['review_status'] == 'accepted']
        sources.append({'source_id': source, 'collection_status': result.collection_status,
                        'pagination_complete': result.pagination_complete,
                        'exception_scan_complete': result.exception_scan_complete,
                        'errors': result.errors, 'triage_counts': triaged['counts'],
                        'candidate_count': len(result.candidates), 'review_required': len(result.review_required),
                        'accepted_count': len(result.accepted_snapshots), 'promotion_decisions': decisions})
    assert baseline == snapshot(), 'source changed during acceptance'
    report = {'snapshot': baseline, 'measured_at': datetime.now(UTC).isoformat(), 'sources': sources,
              'regular_exception_readiness': 'NOT READY', 'production_promoted': False,
              'scope': 'date_specific_official_notice_only',
              'next': 'End-to-End Demo Acceptance; no further unbounded collector repairs'}
    write_new(output / 'live_acceptance.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'snapshot'}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('evals/results/source_repair_20261007/live'))
    parser.add_argument('--target-date', default='2026-10-07')
    parser.add_argument('--registry-in', type=Path)
    parser.add_argument('--review-in', type=Path)
    parser.add_argument('--registry-out', type=Path)
    parser.add_argument('--expected-hash')
    args = parser.parse_args()
    registry = read(args.registry_in) if args.registry_in else {'policy': POLICY, 'version': 1, 'entries': inherited_reviews()}
    if args.review_in:
        if not args.registry_in or not args.registry_out or not args.expected_hash:
            parser.error('registry revision requires input/output and expected hash')
        revised = revise_registry(registry, read(args.review_in), PROFILES, expected_hash=args.expected_hash)
        write_new(args.registry_out, revised)
        print('New registry version written. No production promotion or deployment.')
    else:
        asyncio.run(run(args.output, args.target_date, registry))


if __name__ == '__main__':
    main()
