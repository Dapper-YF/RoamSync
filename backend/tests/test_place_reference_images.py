import asyncio
from functools import wraps
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.external_facts import SearchFact
from app.place_content.provider import normalize_poi
from app.place_content.reference_images import PlaceReferenceImages
from app.place_content.routes import create_router

def place(city='苏州市', name='拙政园', pid='B020001R2Q'):
    return normalize_poi({'id':pid,'name':name,'cityname':city,'location':'120.629,31.324','typecode':'110000'})

def fact(description='苏州拙政园园景'):
    return SearchFact('tavily','2026-10-25T08:00:00Z','query',{'results':[{'url':'https://example.org/place','title':'参考资料'}],
        'images':[{'url':'https://images.example.org/garden.jpg','description':description,'score':.9}]})

def run_async(func):
    @wraps(func)
    def run(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return run

@run_async
async def test_reference_image_reuses_verified_identity_without_repository_or_formal_writes():
    actual=place();calls=[]
    async def detail(ref):
        calls.append(('amap',ref));return actual
    async def search(settings,**kwargs):
        calls.append(('search',kwargs));return fact()
    service=PlaceReferenceImages(SimpleNamespace(detail=detail),Settings(_env_file=None),search=search)
    a,b=await asyncio.gather(*(service.lookup(actual.ref.place_id,'B020001R2Q') for _ in range(2)))
    assert a==b and a['status']=='available'
    assert len(calls)==2
    assert calls[1][1]['query']=='苏州市 拙政园 实景照片'
    assert a['images'][0]['usage_basis']=='search_reference'
    assert 'license_name' not in a['images'][0]
    assert 'not_verified_scene' in a['semantics']
    assert await service.lookup(actual.ref.place_id,'B020001R2Q')==a and len(calls)==2

@pytest.mark.parametrize('case',['canonical_mismatch','provider_mismatch','no_city','unavailable','other_city','unsafe_url','timeout'])
@run_async
async def test_missing_unsafe_or_mismatched_photos_do_not_become_place_photos(case):
    actual=place();calls=[]
    async def detail(ref):
        calls.append('amap')
        if case=='provider_mismatch':return place(pid='OTHER')
        if case=='no_city':return actual.model_copy(update={'city':None})
        if case=='unavailable':return None
        if case=='timeout':raise TimeoutError('secret provider detail')
        return actual
    async def search(settings,**kwargs):
        calls.append('search')
        data=fact('杭州拙政园园景' if case=='other_city' else '苏州拙政园园景')
        if case=='unsafe_url':data.payload['images'][0]['url']='http://127.0.0.1/secret'
        return data
    service=PlaceReferenceImages(SimpleNamespace(detail=detail),Settings(_env_file=None),search=search)
    result=await service.lookup(uuid4() if case=='canonical_mismatch' else actual.ref.place_id,'B020001R2Q')
    assert result['status']=='unavailable' and result['images']==[]
    assert 'secret' not in str(result)
    if case=='canonical_mismatch':assert calls==[]

def test_read_endpoint_validates_both_ids_and_never_accepts_arbitrary_query():
    calls=[]
    async def lookup(*args):calls.append(args);return {'status':'unavailable','images':[]}
    app=FastAPI();app.include_router(create_router(SimpleNamespace(),reference_images=SimpleNamespace(lookup=lookup)))
    actual=place()
    with TestClient(app) as client:
        path=f'/api/v1/places/{actual.ref.place_id}/reference-images'
        assert client.get(path).status_code==422
        assert client.get(path,params={'provider_place_id':'https://private.invalid/'}).status_code==422
        assert client.get(path,params={'provider_place_id':'B020001R2Q'}).status_code==200
    assert calls==[(actual.ref.place_id,'B020001R2Q')]

@run_async
async def test_generic_dish_image_cannot_illustrate_a_named_branch():
    actual=place(name='海底捞火锅(园区店)');calls=[]
    async def detail(ref):return actual
    async def search(settings,**kwargs):calls.append(kwargs);return fact('苏州火锅 hotpot')
    service=PlaceReferenceImages(SimpleNamespace(detail=detail),Settings(_env_file=None),search=search)
    assert (await service.lookup(actual.ref.place_id,'B020001R2Q'))['images']==[]
    assert len(calls)==1

@run_async
async def test_invalid_place_is_negatively_cached():
    calls=[]
    async def detail(ref):calls.append(ref);return None
    service=PlaceReferenceImages(SimpleNamespace(detail=detail),Settings(_env_file=None))
    for _ in range(2):assert (await service.lookup(place().ref.place_id,'B020001R2Q'))['images']==[]
    assert len(calls)==1

@run_async
async def test_chinese_provider_title_can_identify_an_english_description():
    actual=place()
    async def detail(ref):return actual
    async def search(settings,**kwargs):
        data=fact('Visitors explore a classical garden.')
        data.payload['images'][0]['title']='苏州市园林局 · 拙政园'
        return data
    service=PlaceReferenceImages(SimpleNamespace(detail=detail),Settings(_env_file=None),search=search)
    assert (await service.lookup(actual.ref.place_id,'B020001R2Q'))['status']=='available'
