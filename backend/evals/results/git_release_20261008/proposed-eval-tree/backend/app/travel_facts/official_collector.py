"""Deterministic, file-reviewable official source acquisition. No DB or Agent imports.

Offline lifecycle tooling; deliberately not registered in production composition.
Collection completeness concerns a configured listing, never all official channels.
"""
import asyncio
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .opening_hours import plain, reviewed_schedule

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

@dataclass(frozen=True)
class SourceProfile:
    source_id: str
    venue_ref: str
    organization: str
    branch: str
    domain: str
    endpoint: str
    section: str
    schema_version: str
    parser_profile: str
    page_size: int = 100
    pagination: str = 'total'
    max_pages: int = 100
    aliases: tuple = ()

PROFILES={
    'nanjing_museum':SourceProfile('nanjing_museum','amap:B001907TGR','南京博物院','main','www.njmuseum.com',
        'https://www.njmuseum.com/api/news/freshNotice','official notices','nanjing-cms-v1','reviewed-2026-nanjing',aliases=('南京博物院','我院')),
    'zhejiang_museum':SourceProfile('zhejiang_museum','amap:B0I15SU50Z','浙江省博物馆','之江馆区','www.zjmuseum.com.cn',
        'https://www.zjmuseum.com.cn/api/content/page','Notice/site22','zhejiang-cms-v1','reviewed-2026-zhejiang',aliases=('浙江省博物馆之江馆区','之江馆区')),
}

class SchemaChanged(ValueError): pass
class CollectionIncomplete(ValueError): pass

@dataclass
class SourceCollectionResult:
    source_id: str
    venue_ref: str
    fetched_at: str
    collection_status: str = 'collection_incomplete'
    schema_status: str = 'valid'
    pagination_complete: bool = False
    exception_scan_complete: bool = False
    candidates: list = field(default_factory=list)
    accepted_snapshots: list = field(default_factory=list)
    review_required: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    duplicate_count: int = 0
    stop_reason: str = ''
    schema_fingerprint: str = ''

async def official_page(profile, page, cursor=None):
    if urlparse(profile.endpoint).scheme!='https' or urlparse(profile.endpoint).hostname!=profile.domain:
        raise ValueError('untrusted source profile')
    form=profile.source_id=='nanjing_museum'
    params={'language':'zh'} if form else {'siteId':22,'categoryCode':'Notice'}
    params.update(pageNum=page,pageSize=profile.page_size)
    def fetch():
        request=Request(profile.endpoint,data=(urlencode(params) if form else json.dumps(params)).encode(),
            headers={'Content-Type':'application/x-www-form-urlencoded' if form else 'application/json'})
        with urlopen(request,timeout=20) as response: raw=response.read(8_388_609)
        if len(raw)>8_388_608: raise ValueError('page too large')
        return json.loads(raw)
    return await asyncio.to_thread(fetch)

def decode_page(profile, payload, page):
    try:
        if profile.pagination=='cursor':
            # Generic testable engine; neither real source claims cursor support.
            rows=payload['items'];cursor=payload['next_cursor'];total=payload.get('total')
        elif profile.source_id=='nanjing_museum':
            if payload['code']!=0: raise SchemaChanged('CMS status')
            rows=payload['data']['list'];total=payload['data']['total'];cursor=None
            if 'count' in payload and payload['count']!=total: raise CollectionIncomplete('count_total_disagreement')
        else:
            if payload['success'] is not True: raise SchemaChanged('CMS status')
            meta=payload['data'][1][0];rows=payload['data'][2];total=meta['total'];cursor=None
            if meta['pageCurrent']!=page or meta['pageSize']!=profile.page_size:
                raise CollectionIncomplete('page_metadata_mismatch')
            if meta['totalPage']!=math.ceil(total/profile.page_size): raise CollectionIncomplete('total_pages_mismatch')
        if not isinstance(rows,list) or (total is not None and (type(total)!=int or total<0)):
            raise SchemaChanged('listing types')
        if len(rows)>profile.page_size: raise CollectionIncomplete('page_size_exceeded')
        return rows,total,cursor
    except (KeyError,IndexError,TypeError) as exc: raise SchemaChanged('listing_contract_changed') from exc

def normalize(profile,row):
    fields=('id','title','introduction','time') if profile.source_id=='nanjing_museum' else ('content_id','title','content','publish_date')
    try:
        identity,title,body,published=(row[k] for k in fields)
        if type(identity)!=int or not isinstance(title,str) or not title.strip() or not isinstance(body,str):
            raise SchemaChanged('notice_required_field_type')
        # Empty body is represented explicitly and prevents exception completeness;
        # it cannot silently become a missing irrelevant notice.
        fmt=r'\d{4}-\d{2}-\d{2}' if profile.source_id=='nanjing_museum' else r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}'
        if not isinstance(published,str) or not re.fullmatch(fmt,published): raise SchemaChanged('publication_format_changed')
        datetime.fromisoformat(published)
        updated=row.get('update_time')
        if updated is not None and (not isinstance(updated,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',updated)):
            raise SchemaChanged('update_format_changed')
        content={'notice_id':str(identity),'title':title,'body':body,'publication':published,'updated':updated}
        text=plain(body)
        relevant=bool(re.search(r'(?:开放时间|开馆时间|停止入馆|停止入场|闭馆|暂停开放|临时关闭|维修)',title+' '+text))
        scope='main' if profile.source_id=='nanjing_museum' else 'ambiguous'
        if profile.source_id=='nanjing_museum' and re.search(r'非遗馆|展厅|停车场|图书馆',title): scope='subvenue'
        if profile.source_id=='nanjing_museum' and '南京市博物馆' in title+' '+text: scope='other_venue'
        if profile.source_id=='zhejiang_museum':
            if '之江馆区' in text: scope='之江馆区'  # retain full body; parser has a separate section gate
            elif '孤山馆区' in text: scope='孤山馆区'
        years=sorted(set(re.findall(r'(?<!\d)(20\d{2})年',text)))
        html_shape=digest(re.findall(r'</?([a-zA-Z0-9]+)',body))
        result={**content,'content_hash':digest(content),'semantic_hash':digest({'title':title,'body':text}),
            'html_fingerprint':html_shape,'payload_hash':digest(row),'schema_version':profile.schema_version,
            'source_id':profile.source_id,'canonical_venue_ref':profile.venue_ref,'source_organization':profile.organization,
            'branch_scope':scope,'announcement_scope':('multi_branch' if '之江馆区' in text and '孤山馆区' in text else 'branch') if profile.source_id=='zhejiang_museum' else scope,
            'source_url':f'https://{profile.domain}/zh/newsDetails?id={identity}' if profile.source_id=='nanjing_museum' else f'https://{profile.domain}/cn/#/Notice',
            'source_api':profile.endpoint,'parser_profile':profile.parser_profile,'date_scope':{'explicit_years':years,'effective_ranges':[]},
            'review_status':'review_required' if relevant else 'rejected','review_reason':'operational_candidate' if relevant else 'not_operational_schedule',
            'raw_notice':row}
        if not body.strip(): result.update(review_status='review_required',review_reason='body_empty_unknown_scope')
        if relevant and scope not in (profile.branch,): result.update(review_status='review_required',review_reason='scope_requires_review')
        # Date applicability is supplied only by an accepted review, never from a
        # keyword or publication date. Candidate date hints are not effective dates.
        return result
    except (KeyError,TypeError,ValueError) as exc:
        if isinstance(exc,SchemaChanged): raise
        raise SchemaChanged('notice_contract_changed') from exc

def review_entry(candidate, *, status, reviewer, reviewed_at, date_ranges, reason, supersedes=()):
    if status not in {'accepted','rejected'} or not reviewer or not reason: raise ValueError('explicit review required')
    if status=='accepted' and (not date_ranges or candidate['branch_scope'] not in {'main','之江馆区'}):
        raise ValueError('accepted source requires reviewed venue and date scope')
    for first,last in date_ranges:
        if datetime.fromisoformat(first)>datetime.fromisoformat(last): raise ValueError('invalid reviewed date scope')
    return {k:candidate[k] for k in ('source_id','notice_id','content_hash','html_fingerprint','canonical_venue_ref','branch_scope','schema_version')}|{
        'review_status':status,'reviewer':reviewer,'reviewed_at':reviewed_at,'effective_ranges':date_ranges,'reason':reason,'supersedes':list(supersedes)}

def apply_reviews(result, profile, reviews):
    registry={(r['source_id'],r['notice_id']):r for r in reviews}
    for candidate in result.candidates:
        if candidate.get('duplicate_of'):
            candidate.update(review_status='rejected',review_reason='duplicate_content')
            continue
        review=registry.get((profile.source_id,candidate['notice_id']))
        if review:
            if any(review[k]!=candidate[k] for k in ('canonical_venue_ref','branch_scope','schema_version')):
                candidate.update(review_status='review_required',review_reason='review_scope_changed')
            elif review['content_hash']!=candidate['content_hash']:
                state='schema_changed' if review['html_fingerprint']!=candidate['html_fingerprint'] else 'source_changed'
                candidate.update(review_status=state,review_reason='content_requires_re_review')
                if state=='schema_changed':
                    result.schema_status='changed';result.collection_status='schema_changed'
            else:
                candidate.update(review_status=review['review_status'],review=review)
                candidate['date_scope']['effective_ranges']=review['effective_ranges']
        if candidate['review_status'] not in {'rejected','accepted'}: result.review_required.append(candidate['notice_id'])
    # Explicitly reviewed revisions only; later publication by itself does not
    # supersede an independent notice. Overlapping scope and authority required.
    accepted=[c for c in result.candidates if c['review_status']=='accepted']
    by_id={c['notice_id']:c for c in accepted}
    for new in accepted:
        for old_id in new['review'].get('supersedes',[]):
            old=by_id.get(old_id)
            if not old: continue
            if (old['canonical_venue_ref']==new['canonical_venue_ref'] and old['branch_scope']==new['branch_scope']
                and old['date_scope']==new['date_scope'] and new['publication']>old['publication']
                and re.search(r'修订|调整为|更正|替代',plain(new['body']))):
                old['review_status']='superseded'
            else: new.update(review_status='review_required',review_reason='supersession_not_proven')
    result.review_required=list(dict.fromkeys([*result.review_required,*[c['notice_id'] for c in result.candidates if c['review_status'] not in {'accepted','rejected','superseded'}]]))
    result.accepted_snapshots=[dict(c) for c in result.candidates if c['review_status']=='accepted'] if result.pagination_complete and result.schema_status=='valid' else []
    result.exception_scan_complete=bool(result.pagination_complete and result.schema_status=='valid' and not result.review_required
        and all(c['branch_scope'] not in {'ambiguous','subvenue'} for c in result.candidates if c['review_status']!='rejected'))

async def collect(profile, *, gateway=official_page, reviews=(), progress=None):
    result=SourceCollectionResult(profile.source_id,profile.venue_ref,datetime.now(UTC).isoformat())
    result.schema_fingerprint=digest({'profile':profile.schema_version,'pagination':profile.pagination,'required_notice_fields':
        ['id','title','introduction','time'] if profile.source_id=='nanjing_museum' else ['content_id','title','content','publish_date']})
    seen_ids={};seen_contents={};seen_pages=set();seen_cursors=set();total_expected=None;cursor=None
    try:
        for page in range(1,profile.max_pages+1):
            payload=await gateway(profile,page,cursor);rows,total,next_cursor=decode_page(profile,payload,page)
            fingerprint=digest(rows)
            result.pages.append({'page':page,'page_size':profile.page_size,'items':len(rows),'total':total,'cursor':cursor,
                'next_cursor':next_cursor,'payload_hash':digest(payload),'fetched_at':datetime.now(UTC).isoformat()})
            if progress: progress(result.pages[-1])
            if total_expected is not None and total!=total_expected: raise CollectionIncomplete('inconsistent_total')
            total_expected=total
            if fingerprint in seen_pages and rows: raise CollectionIncomplete('duplicated_page')
            seen_pages.add(fingerprint)
            for row in rows:
                try: candidate=normalize(profile,row)
                except SchemaChanged as exc:
                    result.schema_status='changed'
                    identity=str(row.get('id',row.get('content_id','unknown'))) if isinstance(row,dict) else 'unknown'
                    result.errors.append(f'notice:{identity}:{exc}')
                    result.review_required.append('schema:'+identity)
                    continue
                identity=candidate['notice_id'];content=candidate['content_hash']
                if identity in seen_ids:
                    result.duplicate_count+=1
                    if seen_ids[identity]!=content: raise CollectionIncomplete('same_id_changed_during_scan')
                    continue
                seen_ids[identity]=content
                semantic=candidate['semantic_hash']
                if semantic in seen_contents:
                    result.duplicate_count+=1;candidate.update(review_status='rejected',review_reason='duplicate_content',duplicate_of=seen_contents[semantic])
                else: seen_contents[semantic]=identity
                result.candidates.append(candidate)
            if profile.pagination=='total':
                expected=min(profile.page_size,max(total-(page-1)*profile.page_size,0))
                if len(rows)!=expected: raise CollectionIncomplete('missing_or_empty_page')
                if page*profile.page_size>=total:
                    # CMS totals describe listed entries, including repeated IDs.
                    # Exhaust physical pages; deduplication is a separate count.
                    if sum(p['items'] for p in result.pages)!=total: raise CollectionIncomplete('entry_count_disagrees_with_total')
                    result.pagination_complete=True;result.stop_reason='total_exhausted';break
            else:
                if next_cursor is None:
                    result.pagination_complete=True;result.stop_reason='next_cursor_absent';break
                if next_cursor in seen_cursors: raise CollectionIncomplete('cursor_loop')
                seen_cursors.add(next_cursor);cursor=next_cursor
        else: raise CollectionIncomplete('page_limit_reached')
        # A second pass verifies every page, detecting ordering/content changes.
        # This is observed stability, not an atomic CMS snapshot guarantee.
        for record in result.pages:
            checked=await gateway(profile,record['page'],record['cursor'])
            again,t,_=decode_page(profile,checked,record['page'])
            if digest(checked)!=record['payload_hash'] or t!=total_expected: raise CollectionIncomplete('listing_changed_during_scan')
            record['stability_recheck']=True
        result.collection_status='complete' if result.schema_status=='valid' else 'schema_changed'
    except SchemaChanged as exc:
        result.collection_status='schema_changed';result.schema_status='changed';result.errors.append(str(exc));result.pagination_complete=False
    except CollectionIncomplete as exc:
        result.errors.append(str(exc));result.pagination_complete=False;result.collection_status='collection_incomplete'
    except Exception as exc:
        result.errors.append('fetch_unavailable:'+type(exc).__name__);result.pagination_complete=False
    apply_reviews(result,profile,reviews)
    return result

def accepted_payload(profile, snapshot):
    """Bridge an accepted source to the existing reviewed parser; no new Fact contract."""
    if snapshot['review_status']!='accepted' or snapshot['canonical_venue_ref']!=profile.venue_ref:
        raise ValueError('source not accepted for venue')
    normalized=normalize(profile,snapshot['raw_notice'])
    if normalized['content_hash']!=snapshot['review']['content_hash']: raise ValueError('accepted snapshot modified')
    row=snapshot['raw_notice']
    return {'code':0,'data':{'list':[row]}} if profile.source_id=='nanjing_museum' else {'success':True,'data':[None,None,[row]]}
