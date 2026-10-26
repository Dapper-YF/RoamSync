import asyncio
import copy
from dataclasses import replace
from datetime import datetime
import pytest

from app.travel_facts.official_collector import (PROFILES, collect, normalize, review_entry, accepted_payload, digest)
from test_opening_hours import payload

P=replace(PROFILES['nanjing_museum'],page_size=2)
RAW=payload('nanjing_museum')['data']['list'][0]
def notice(identity,body=None,title=None):
    raw=copy.deepcopy(RAW);raw['id']=identity
    if body is not None: raw['introduction']=body
    if title is not None: raw['title']=title
    return raw
def page(rows,total): return {'code':0,'count':total,'data':{'list':rows,'total':total}}
def accepted(raw=RAW,**kwargs):
    return review_entry(normalize(P,raw),status='accepted',reviewer='fixture reviewer',reviewed_at='2026-10-01',
        date_ranges=[['2026-10-01','2026-10-07']],reason='reviewed exact source',**kwargs)
def run(pages,profile=P,reviews=()):
    async def gateway(profile,page_number,cursor):
        value=pages[page_number-1]
        if isinstance(value,Exception): raise value
        return copy.deepcopy(value)
    return asyncio.run(collect(profile,gateway=gateway,reviews=reviews))

def test_single_page_accepted_snapshot_is_separate_from_discovery():
    result=run([page([RAW],1)],reviews=[accepted()])
    assert result.pagination_complete and result.collection_status=='complete'
    assert len(result.accepted_snapshots)==1 and result.exception_scan_complete
    assert accepted_payload(P,result.accepted_snapshots[0])['data']['list'][0]['id']==RAW['id']

def test_page_two_notice_found_without_id_entrypoint():
    result=run([page([notice(1,'x','展览'),notice(2,'y','工作')],3),page([RAW],3)],reviews=[accepted()])
    assert len(result.pages)==2 and result.pagination_complete and result.accepted_snapshots[0]['notice_id']==str(RAW['id'])
    assert result.stop_reason=='total_exhausted'

def test_duplicate_entry_not_independent_source():
    result=run([page([RAW,notice(2)],2)],reviews=[accepted()])
    assert result.pagination_complete and result.duplicate_count==1 and len(result.accepted_snapshots)==1

@pytest.mark.parametrize('broken',[TimeoutError(),{},page([],3),page([notice(3)],4)])
def test_page_failure_never_means_no_exception(broken):
    result=run([page([RAW,notice(2,'x','展览')],3),broken],reviews=[accepted()])
    assert not result.pagination_complete and not result.exception_scan_complete and not result.accepted_snapshots and result.errors

def test_duplicate_page_is_not_exhaustion():
    first=page([RAW,notice(2)],4)
    result=run([first,first],reviews=[accepted()])
    assert result.stop_reason=='' and result.errors==['duplicated_page']

def test_known_total_zero_requires_empty_page():
    result=run([page([],0)])
    assert result.pagination_complete and result.exception_scan_complete

def test_cursor_page_two_and_empty_final_page():
    profile=replace(P,pagination='cursor')
    result=run([{'items':[RAW],'next_cursor':'two'},{'items':[],'next_cursor':None}],profile,reviews=[accepted()])
    assert result.pagination_complete and result.pages[1]['cursor']=='two' and result.stop_reason=='next_cursor_absent'

def test_cursor_loop_fails_closed():
    profile=replace(P,pagination='cursor')
    result=run([{'items':[RAW],'next_cursor':'same'},{'items':[notice(2,'different')],'next_cursor':'same'}],profile)
    assert not result.pagination_complete and 'cursor_loop' in result.errors

@pytest.mark.parametrize('mutation',['content_rename','id_missing','title_missing','body_missing','date_format','nested_changed'])
def test_required_schema_drift_is_explicit(mutation):
    raw=copy.deepcopy(RAW)
    if mutation=='content_rename': raw['content']=raw.pop('introduction')
    elif mutation=='id_missing': raw.pop('id')
    elif mutation=='title_missing': raw.pop('title')
    elif mutation=='body_missing': raw.pop('introduction')
    elif mutation=='date_format': raw['time']='17/09/2026'
    result=run([{'code':0,'data':{'items':[raw],'total':1}} if mutation=='nested_changed' else page([raw],1)],reviews=[accepted()])
    assert result.collection_status=='schema_changed' and result.schema_status=='changed'
    assert not result.exception_scan_complete and not result.accepted_snapshots

def test_same_id_changed_content_requires_review():
    raw=notice(RAW['id'],RAW['introduction'].replace('20:00','18:00'))
    result=run([page([raw],1)],reviews=[accepted()])
    assert result.pagination_complete and not result.accepted_snapshots and not result.exception_scan_complete
    assert result.candidates[0]['review_status']=='source_changed'

def test_html_shape_drift_detected_without_silent_empty():
    raw=notice(RAW['id'],'<div>'+RAW['introduction']+'</div>')
    result=run([page([raw],1)],reviews=[accepted()])
    assert result.candidates[0]['review_status']=='schema_changed' and result.review_required

def test_new_candidate_not_promoted_rejected_not_promoted():
    candidate=normalize(P,RAW)
    assert run([page([RAW],1)]).candidates[0]['review_status']=='review_required'
    rejected=review_entry(candidate,status='rejected',reviewer='fixture',reviewed_at='2026-10-01',date_ranges=[],reason='rejected fixture')
    assert not run([page([RAW],1)],reviews=[rejected]).accepted_snapshots

def test_unchanged_fetch_does_not_require_new_review():
    assert not run([page([RAW],1)],reviews=[accepted()]).review_required

def test_scope_nanjing_hall_not_main_and_exhibition_not_hours():
    assert normalize(P,notice(1,'国庆特别展览','国庆特别展览公告'))['review_status']=='rejected'
    assert normalize(P,notice(2,'临时闭馆','非遗馆展厅延期开放'))['branch_scope']=='subvenue'
    with pytest.raises(ValueError): accepted(notice(2,'临时闭馆','非遗馆展厅延期开放'))
    assert normalize(P,notice(3,'南京市博物馆开放时间','南京市博物馆开馆公告'))['branch_scope']=='other_venue'

def test_zhejiang_scope_binding_does_not_leak_between_branches():
    profile=PROFILES['zhejiang_museum'];raw=payload('zhejiang_museum')['data'][2][0]
    assert normalize(profile,raw)['branch_scope']=='之江馆区'
    for body,expected in [('浙江省博物馆临时闭馆','ambiguous'),('孤山馆区临时闭馆','孤山馆区')]:
        altered=dict(raw,content=body)
        candidate=normalize(profile,altered)
        assert candidate['branch_scope']==expected and candidate['review_status']=='review_required'
        if expected=='ambiguous':
            with pytest.raises(ValueError): review_entry(candidate,status='accepted',reviewer='x',reviewed_at='2026-10-01',date_ranges=[['2026-10-01','2026-10-07']],reason='x')

def test_listing_order_change_during_scan_incomplete():
    n=0
    async def gateway(*args):
        nonlocal n;n+=1
        return page([RAW,notice(2,'x','展览')] if n==1 else [notice(2,'x','展览'),RAW],2)
    result=asyncio.run(collect(P,gateway=gateway,reviews=[accepted()]))
    assert 'listing_changed_during_scan' in result.errors and not result.accepted_snapshots

def test_snapshot_tampering_rejected():
    snapshot=run([page([RAW],1)],reviews=[accepted()]).accepted_snapshots[0]
    snapshot['raw_notice']['introduction']='altered'
    with pytest.raises(ValueError): accepted_payload(P,snapshot)

def test_explicit_reviewed_supersession_only():
    old=notice(1);new=notice(2,'修订调整为 '+RAW['introduction'].replace('20:00','18:00'))
    new['time']='2026-09-18';reviews=[accepted(old),accepted(new,supersedes=['1'])]
    result=run([page([old,new],2)],reviews=reviews)
    assert result.candidates[0]['review_status']=='superseded' and len(result.accepted_snapshots)==1
    new['introduction']=RAW['introduction'].replace('20:00','18:00')
    result=run([page([old,new],2)],reviews=[accepted(old),accepted(new)])
    assert len(result.accepted_snapshots)==2  # resolver, not publication recency, arbitrates independent evidence

def test_unique_count_not_required_when_cms_lists_duplicate_ids():
    result=run([page([RAW,RAW],2)],reviews=[accepted()])
    assert result.pagination_complete and result.duplicate_count==1 and len(result.accepted_snapshots)==1

def test_later_page_order_change_detected_by_full_second_pass():
    calls={}
    async def gateway(profile,page_number,cursor):
        calls[page_number]=calls.get(page_number,0)+1
        if page_number==1: return page([RAW,notice(2,'x','展览')],4)
        rows=[notice(3,'y','展览'),notice(4,'z','展览')]
        return page(rows if calls[2]==1 else list(reversed(rows)),4)
    result=asyncio.run(collect(P,gateway=gateway,reviews=[accepted()]))
    assert 'listing_changed_during_scan' in result.errors and not result.exception_scan_complete

def test_bad_historical_row_invalidates_truth_but_preserves_page_traversal():
    # Explicit null body, not helper's default body.
    bad=notice(3);bad['introduction']=None
    result=run([page([RAW,notice(2,'x','展览')],3),page([bad],3)],reviews=[accepted()])
    assert result.pagination_complete and result.collection_status=='schema_changed'
    assert not result.accepted_snapshots and not result.exception_scan_complete and result.errors
