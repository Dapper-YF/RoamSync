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
    assert "大家都说" not in bundle["assistant"] and "只取得搜索摘要" in bundle["assistant"]
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
    bundle=asyncio.run(research(None,'火锅',[],ContextEnvelope(browsing_city='成都'),Port(),judge=judge,search=search,answer=answer))
    assert '99' not in bundle['assistant'] and '不排队' not in bundle['assistant'] and '没有可展示' not in bundle['assistant']
    assert '4.6' in bundle['assistant']
    assert set(bundle['read_tools']['web_search']['answer_validation']) == {'unsupported_numeric_claim','review_claim_without_review_source','model_media_availability_claim'}
