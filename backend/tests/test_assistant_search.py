import asyncio
from datetime import UTC, datetime

import pytest

from app.assistant_search import project_search, public_image_url, search_requested, search_subject
from app.external_facts import SearchFact


def fact(images):
    return SearchFact("tavily", datetime.now(UTC).isoformat(), "q", {"results": [{"url": "https://example.org/page", "title": "旅游参考", "content": "检索片段"}], "images": images})


@pytest.mark.parametrize("value", ["http://example.org/x", "https://127.0.0.1/x", "https://10.0.0.1/x", "https://[::1]/x", "https://localhost/x", "https://foo.local/x", "https://user:secret@example.org/x", "javascript:alert(1)", "https://example.org/x?api_key=secret"])
def test_unsafe_media_urls_not_projected(value):
    assert public_image_url(value) is None


def test_exact_subject_image_no_same_city_substitution_and_no_city_allowlist():
    images = [{"url": "https://images.example.org/1.jpg", "description": "南京玄武湖风景"}, {"url": "https://images.example.org/2.jpg", "description": "南京博物院建筑"}]
    result = project_search(fact(images), "请联网搜索南京博物院的图片")
    assert [i["description"] for i in result["images"]] == ["南京博物院建筑"]
    assert search_subject("联网搜索北京故宫的图片") == "北京故宫"
    assert project_search(fact([{"url": "https://images.example.org/p.jpg", "description": "北京故宫建筑"}]), "联网搜索北京故宫的图片")["images"]


def test_food_image_requires_food_content_and_preserves_provider_only_urls():
    result = project_search(fact([{"url": "https://images.example.org/street.jpg", "description": "成都街头"}, {"url": "https://images.example.org/pot.jpg", "description": "成都火锅美食"}]), "联网搜索成都有什么特色美食")
    assert len(result["images"]) == 1
    assert result["images"][0]["url"].endswith("pot.jpg")
    assert result["semantics"] == "search_reference_not_verified_fact"
    assert not search_requested("成都有什么特色美食")


def test_returned_encoded_filename_can_ground_image_without_invented_caption():
    from urllib.parse import quote
    result = project_search(fact([{"url": "https://images.example.org/" + quote("成都四川火锅.jpg")}]), "联网搜索成都有什么特色美食")
    assert result["images"][0]["description"] == "成都四川火锅"
    assert not project_search(fact([{"url": "https://images.example.org/" + quote("南京玄武湖.jpg")}]), "联网搜索南京博物院的图片")["images"]


def test_dish_reference_does_not_claim_city_photograph_or_replace_a_venue():
    image = {"url": "https://images.example.org/photo.jpg", "description": "A spicy hotpot with chili"}
    result = project_search(fact([image]), "联网搜索成都有什么特色美食，想看看火锅图片")
    assert result["images"][0]["topic"] == "火锅"
    assert result["images"][0]["description"].startswith("火锅参考图")
    assert not project_search(fact([image]), "联网搜索南京博物院的图片")["images"]


def test_search_context_never_becomes_verified_evidence_or_authority():
    from app.companion_contracts import CompanionDraft
    from app.companion_runtime import CompanionRuntime
    from app.travel_goal_router import route_travel_goal
    class Reader:
        async def load(self, context, need): return context
    class Provider:
        async def generate(self, context, need):
            assert need.general_knowledge_allowed
            assert not context.knowledge_context
            assert context.read_tool_context["web_search"]["status"] == "available"
            return CompanionDraft(response_text="可以先比较火锅与街头小吃的体验。")
    text = "请联网搜索成都有什么特色美食"
    result = asyncio.run(CompanionRuntime(Reader(), Provider()).run(session_id="s", turn_id="t", message=text,
        goal=route_travel_goal(text), messages=[], read_tool_context={"web_search": project_search(fact([]), text)}))
    assert not result.knowledge_evidence
    assert not result.answer_evidence_refs
    assert not result.planning_handoff
