"""Official listing rediscovery and explicit inherited-v1 file reviews; no DB writes."""
import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from app.travel_facts.official_collector import PROFILES, collect, normalize, review_entry, accepted_payload
from app.travel_facts.opening_hours import reviewed_schedule
from evals.phase25_final import snapshot

OUT=Path(__file__).parent/'results/opening_collector'

def inherited_reviews():
    rows=[]
    for provider,name in [('nanjing_museum','nanjing'),('zhejiang_museum','zhejiang')]:
        payload=json.loads((Path(__file__).parents[1]/'tests/fixtures/opening_hours'/f'{name}.json').read_text(encoding='utf-8-sig'))
        candidates=payload['data']['list'][:1] if name=='nanjing' else payload['data'][2][:1]
        for raw in candidates:
            candidate=normalize(PROFILES[provider],raw)
            ranges=[['2026-09-25','2026-09-27'],['2026-10-01','2026-10-07']] if name=='nanjing' else [['2026-09-25','2026-10-08']]
            rows.append(review_entry(candidate,status='accepted',reviewer='inherited v1 acceptance: OPENING_HOURS_SOURCE_DECISION_20261001.md',
                reviewed_at='2026-10-01',date_ranges=ranges,reason='Exact existing reviewed source snapshot; no new notice acceptance'))
    return rows

async def run():
    OUT.mkdir(parents=True,exist_ok=True);reviews=inherited_reviews()
    (OUT/'review_registry.json').write_text(json.dumps(reviews,ensure_ascii=False,indent=2),encoding='utf-8')
    async def one(provider):
        profile=PROFILES[provider]
        result=await collect(profile,reviews=reviews,progress=lambda p:print(provider,'page',p['page'],p['items'],p['total'],flush=True))
        (OUT/f'{provider}_discovery.json').write_text(json.dumps(asdict(result),ensure_ascii=False,indent=2),encoding='utf-8')
        matched=[]
        for candidate in result.candidates:
            if candidate['review_status']=='accepted':
                # Record exact inherited review match even when a different row
                # invalidates the collection. Invalid collection emits no truth.
                accepted_for_use=candidate in result.accepted_snapshots
                parsed=reviewed_schedule(provider,accepted_payload(profile,candidate),datetime(2026,10,2).date()) if accepted_for_use else None
                matched.append({'notice_id':candidate['notice_id'],'accepted_content_hash':candidate['content_hash'],
                    'accepted_for_use':accepted_for_use,'native_parser_schedule':parsed})
        proof={'source_id':provider,'snapshot':snapshot(),'collection_status':result.collection_status,'pagination_complete':result.pagination_complete,
            'exception_scan_complete':result.exception_scan_complete,'pages_requested':len(result.pages)+sum(p.get('stability_recheck',False) for p in result.pages),
            'pages':result.pages,'candidate_count':len(result.candidates),'relevant_count':sum(c['review_reason']!='not_operational_schedule' for c in result.candidates),
            'accepted_count':len(result.accepted_snapshots),'duplicate_count':result.duplicate_count,'schema_fingerprint':result.schema_fingerprint,
            'stop_reason':result.stop_reason,'errors':result.errors,'accepted_match':matched,'review_required_count':len(result.review_required)}
        (OUT/f'{provider}_proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
        print(provider,'FINAL',result.collection_status,len(matched),result.errors,flush=True)
        return proof
    proof=await asyncio.gather(*(one(provider) for provider in PROFILES))
    (OUT/'rediscovery.json').write_text(json.dumps({'sources':proof,'snapshot':snapshot(),'measured_at':datetime.now(UTC).isoformat()},ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-input',type=Path)
    parser.add_argument('--notice')
    parser.add_argument('--review-action',choices=['accepted','rejected'])
    parser.add_argument('--reviewer')
    parser.add_argument('--reason')
    parser.add_argument('--dates',nargs=2,action='append',default=[])
    parser.add_argument('--review-output',type=Path)
    args=parser.parse_args()
    if args.review_input:
        if not all([args.notice,args.review_action,args.reviewer,args.reason,args.review_output]):
            parser.error('review requires notice, action, reviewer, reason and output')
        collection=json.loads(args.review_input.read_text(encoding='utf-8-sig'))
        matches=[c for c in collection['candidates'] if c['notice_id']==args.notice]
        if len(matches)!=1: parser.error('review must select exactly one candidate')
        review=review_entry(matches[0],status=args.review_action,reviewer=args.reviewer,reviewed_at=datetime.now(UTC).isoformat(),
            date_ranges=args.dates,reason=args.reason)
        if args.review_output.exists(): parser.error('review artifact exists; write a new version')
        args.review_output.parent.mkdir(parents=True,exist_ok=True)
        args.review_output.write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
        print('review artifact written; not a production deployment')
    else: asyncio.run(run())

if __name__=='__main__': main()
