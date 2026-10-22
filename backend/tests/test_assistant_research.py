import asyncio
import uuid
from datetime import UTC, datetime
from app.assistant_context import ContextEnvelope
from app.assistant_places import PlaceView
from app.assistant_research import LookupIntent, ResearchAnswer, research, identity_matches
from app.external_facts import SearchFact

PLACE = PlaceView(place_id=uuid.uuid4(), name="六公里老火锅(玉林店)", city="成都市", category="food",
    source="https://www.amap.com/search?id=BTEST", retrieved_at=datetime.now(UTC).isoformat(),
    address="电信南街33号", rating=4.6, reference_cost_yuan=68)

class Port:
    async def search(self, **kwargs):
        self.query = kwargs["query"]
        return [PLACE]

def test_followup_cites_actual_page():
    port = Port()
    async def judge(*args): return LookupIntent(needed=True, city="成都", query="火锅")
    async def search(*args, **kwargs):
        return SearchFact("tavily", "2026-10-20T00:00:00Z", "q", {"results": [{"url": "https://example.org/shop", "title": PLACE.name, "content": PLACE.name + " 牛油锅底"}], "images": []})
    async def extract(*args, **kwargs):
        return {"results": [{"url": "https://example.org/shop", "raw_content": PLACE.name + "。这篇探店文章提到牛油锅底比较厚重。"}]}
    async def answer(*args):
        source = next(s for s in args[-1]["sources"] if s["read_level"] == "page_text")
        return ResearchAnswer(paragraphs=[{"text": "文章提到锅底比较厚重，可以作为候选。", "place_index": 1,
            "supports": [{"source_id": source["source_id"], "snippet_id": "s2"}]}])
    bundle = asyncio.run(research(None, "成都哪家好吃", [{"user": "想吃火锅了"}], ContextEnvelope(), port,
        judge=judge, search=search, extract=extract, answer=answer))
    assert port.query == "火锅" and bundle["context"]["browsing_city"] == "成都"
    assert "[2]" in bundle["assistant"]
    assert bundle["read_tools"]["web_search"]["sources"][-1]["read_level"] == "page_text"
    assert bundle["place_cards"][0]["place"]["rating"] == 4.6

def test_unknown_city_does_not_use_invented_city_or_gps():
    async def judge(*args): return LookupIntent(needed=True, city="成都", query="火锅")
    bundle = asyncio.run(research(None, "哪家火锅好吃", [], ContextEnvelope(), Port(), judge=judge))
    assert not bundle["place_cards"] and bundle["companion_result"]["status"] == "needs_clarification"

def test_branch_matching():
    assert not identity_matches(PLACE, "六公里老火锅(春熙路店)", "六公里老火锅的牛油锅")
    assert identity_matches(PLACE, "六公里老火锅 玉林店", "页面")

def test_fake_quote_is_discarded_and_extract_failure_is_not_page_read():
    async def judge(*args): return LookupIntent(needed=True, query="火锅")
    async def search(*args, **kwargs):
        return SearchFact("tavily", "today", "q", {"results": [{"url": "https://example.org/p", "title": PLACE.name, "content": PLACE.name + " 门店信息"}]})
    async def extract(*args, **kwargs): raise TimeoutError()
    async def answer(*args):
        return ResearchAnswer(paragraphs=[{"text": "大家都说不会排队。", "place_index": 1,
            "supports": [{"source_id": args[-1]["sources"][0]["source_id"], "snippet_id": "invented"}]}])
    bundle = asyncio.run(research(None, "火锅", [], ContextEnvelope(browsing_city="成都"), Port(),
        judge=judge, search=search, extract=extract, answer=answer))
    assert "大家都说" not in bundle["assistant"]
    assert all(s["read_level"] != "page_text" for s in bundle["read_tools"]["web_search"]["sources"])
    assert bundle["read_tools"]["web_search"]["sources"][-1]["read_level"] == "search_excerpt"

def test_wrong_requested_branch_not_replaced_and_general_chat_ignored():
    async def judge(*args): return LookupIntent(needed=True, names=["六公里老火锅(春熙路店)"], city="成都")
    bundle = asyncio.run(research(None, "成都六公里老火锅(春熙路店)怎么样", [], ContextEnvelope(), Port(), judge=judge))
    assert not bundle["place_cards"]
    async def no_lookup(*args): return LookupIntent(needed=False)
    assert asyncio.run(research(None, "你好", [], ContextEnvelope(), Port(), judge=no_lookup)) is None

def test_topic_photo_is_never_relabelled_as_a_branch_photo():
    async def judge(*args): return LookupIntent(needed=True, query="火锅")
    async def search(*args, **kwargs):
        return SearchFact("tavily", "today", "q", {"results": [{"url": "https://example.org/p", "title": PLACE.name, "content": PLACE.name}],
            "images": [{"url": "https://images.example.org/hotpot.jpg", "description": "A hotpot and skewers on a table"}]})
    async def extract(*args, **kwargs): return {}
    async def answer(*args): return ResearchAnswer()
    bundle = asyncio.run(research(None, "火锅", [], ContextEnvelope(browsing_city="成都"), Port(), judge=judge, search=search, extract=extract, answer=answer))
    image = bundle["read_tools"]["web_search"]["images"][0]
    assert image["topic"] == "火锅" and image["place_id"] is None
    assert image["description"].startswith("火锅参考图")

def test_real_reference_cannot_authorize_invented_prices_or_reviews():
    async def judge(*args): return LookupIntent(needed=True, query='火锅')
    async def search(*args, **kwargs): return SearchFact('tavily', 'today', 'q', {'results': []})
    async def answer(*args):
        return ResearchAnswer(paragraphs=[{'text':'人均只要99元。用户都说不排队。高德参考评分4.6。本次资料没有可展示的图片。', 'place_index':1,
            'supports':[{'source_id':'poi_1','snippet_id':'s1'}]}])
    bundle=asyncio.run(research(None,'火锅评分',[],ContextEnvelope(browsing_city='成都'),Port(),judge=judge,search=search,answer=answer))
    assert '99' not in bundle['assistant'] and '不排队' not in bundle['assistant'] and '没有可展示' not in bundle['assistant']
    assert '4.6' in bundle['assistant']
    assert set(bundle['read_tools']['web_search']['answer_validation']) == {'unsupported_numeric_claim','review_claim_without_review_source','model_media_availability_claim'}


def test_prose_projection_omits_unasked_provider_parameters_but_keeps_requested_fields():
    from app.assistant_research import prose_place_reference
    experience=prose_place_reference(PLACE, '适合慢慢逛吗', 'attraction')
    assert PLACE.address not in experience and '4.6' not in experience
    practical=prose_place_reference(PLACE, '地址在哪，评分和人均多少', 'food')
    assert PLACE.address in practical and '4.6' in practical and '68' in practical


def test_explicit_named_nearby_anchor_is_resolved_without_assuming_gps():
    park=PLACE.model_copy(update={'name':'人民公园','place_id':uuid.uuid4(),'longitude':104.05,'latitude':30.65})
    class NamedPort:
        async def search(self, **kw):
            if kw['query']=='人民公园': return [park]
            assert kw['near']==park
            return [PLACE]
    async def judge(*a): return LookupIntent(needed=True,city='成都',query='早餐',nearby=True,near_name='人民公园',read_pages=False)
    async def answer(*a): return ResearchAnswer()
    result=asyncio.run(research(None,'成都人民公园附近吃早餐',[],ContextEnvelope(),NamedPort(),judge=judge,answer=answer))
    assert result['place_cards'] and '请指定' not in result['assistant']


def test_personal_fatigue_is_not_a_live_venue_status_question():
    from app.travel_goal_router import route_travel_goal
    from app.companion_contracts import CompanionContext
    from app.companion_information import determine_information_need
    text='我本来今天想去玄武湖，现在累了不想走'
    goal=route_travel_goal(text,[])
    need=determine_information_need(CompanionContext(current_message=text,travel_goal=goal),[])
    assert not need.live_fact_required
    assert route_travel_goal('现在人多吗',[]).live_fact_likely_required


def test_named_attraction_selects_one_main_poi_not_duplicate_alias_cards():
    main=PLACE.model_copy(update={'name':'玄武湖景区','category':'attraction','city':'南京市'})
    alias=main.model_copy(update={'name':'玄武湖','place_id':uuid.uuid4()})
    class AliasPort:
        async def search(self, **kw): return [alias,main]
    async def judge(*a): return LookupIntent(needed=True,city='南京',query='玄武湖',names=['玄武湖'],category='attraction',read_pages=False)
    async def answer(*a): return ResearchAnswer()
    result=asyncio.run(research(None,'南京玄武湖适合散步吗',[],ContextEnvelope(),AliasPort(),judge=judge,answer=answer))
    assert [p['place']['name'] for p in result['place_cards']]==['玄武湖景区']


def test_precise_name_keeps_city_prefix_that_is_part_of_the_place_name():
    museum=PLACE.model_copy(update={'name':'南京博物院','city':'南京市','category':'attraction'})
    class MuseumPort:
        async def search(self, **kw):
            assert kw['query']=='南京博物院'
            return [museum]
    async def judge(*a): return LookupIntent(needed=True,city='南京',query='南京博物院',names=['南京博物院'],category='attraction',read_pages=False)
    async def answer(*a): return ResearchAnswer()
    result=asyncio.run(research(None,'南京博物院值得去吗',[],ContextEnvelope(),MuseumPort(),judge=judge,answer=answer))
    assert len(result['place_cards'])==1


def test_explicit_comparison_can_cite_both_full_place_identities():
    other=PLACE.model_copy(update={'name':'皇城老妈火锅(皇城店)','place_id':uuid.uuid4(),'reference_cost_yuan':115})
    class Both:
        async def search(self,**kw): return [other] if '皇城老妈' in kw['query'] else [PLACE]
    async def judge(*a): return LookupIntent(needed=True,city='成都',names=[PLACE.name,other.name],read_pages=False)
    async def answer(*a): return ResearchAnswer(paragraphs=[{'text':PLACE.name+'参考人均68元，'+other.name+'参考人均115元。','place_index':1,'supports':[{'source_id':'poi_1','snippet_id':'s1'},{'source_id':'poi_2','snippet_id':'s1'}]}])
    result=asyncio.run(research(None,'成都'+PLACE.name+'和'+other.name+'怎么选',[],ContextEnvelope(),Both(),judge=judge,answer=answer))
    assert '[1] [2]' in result['assistant'] and not result['read_tools']['web_search']['answer_validation']


def test_missing_comparison_subject_cannot_be_ranked_as_worse():
    async def judge(*a): return LookupIntent(needed=True,city='成都',names=[PLACE.name,'皇城老妈火锅(皇城店)'],read_pages=False)
    async def answer(*a): raise AssertionError('do not rank incomplete comparison')
    result=asyncio.run(research(None,'成都'+PLACE.name+'和皇城老妈火锅(皇城店)怎么选',[],ContextEnvelope(),Port(),judge=judge,answer=answer))
    assert '暂时不能做完整比较' in result['assistant']
    assert 'comparison_incomplete' in result['read_tools']['web_search']['answer_validation']


def test_public_page_does_not_authorize_current_booking_or_walking_guarantees():
    async def judge(*a): return LookupIntent(needed=True,city='成都',query='火锅',read_pages=False)
    async def answer(*a): return ResearchAnswer(paragraphs=[{'text':'每晚六点放票，必须提前实名预约。全逛步数约两万步，强度很低。可以先看地点详情。','place_index':1,'supports':[{'source_id':'poi_1','snippet_id':'s1'}]}])
    result=asyncio.run(research(None,'成都火锅预约要求',[],ContextEnvelope(),Port(),judge=judge,answer=answer))
    assert '每晚六点' not in result['assistant'] and '强度很低' not in result['assistant']
    assert '没有通过官方渠道确认' in result['assistant']
