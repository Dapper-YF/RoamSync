import asyncio
from datetime import datetime, UTC, timedelta
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.drafts.contracts import DraftPlan
from app.place_content.contracts import Place
from app.conversation_candidate.service import resolve_plan


def plan(item):
    return DraftPlan.model_validate({"schema_version":2,"schedule_constraints":{
        "start_date":"2026-11-09","daily_start_time":"10:00","daily_end_time":"18:00","transport_mode":"walk"},
        "days":[{"day_index":1,"title":"一天","items":[item]}]})


def test_explicit_interval_is_valid_duration_evidence():
    value=plan({"item_ref":"lunch","kind":"meal","name":"午餐","start_time":"12:00","end_time":"13:00",
        "duration_minutes":60,"duration_source":"user_explicit","source_quote":"12:00至13:00保留午餐"})
    result=asyncio.run(resolve_plan(value,"成都",SimpleNamespace(),[],"12:00至13:00保留午餐"))
    assert result.days[0].items[0].duration_minutes==60


def test_model_finish_clock_cannot_replace_user_available_day_boundary():
    value=plan({"item_ref":"lunch","kind":"meal","name":"午餐","duration_minutes":60,"source_quote":"中午留一小时吃饭"})
    value.days[0].start_time=datetime.strptime("10:00","%H:%M").time()
    value.days[0].end_time=datetime.strptime("15:30","%H:%M").time()
    result=asyncio.run(resolve_plan(value,"成都",SimpleNamespace(),[],"10点出发，18点前结束，中午留一小时吃饭"))
    assert result.days[0].start_time is None and result.days[0].end_time is None
    assert result.schedule_constraints.daily_end_time.hour==18


@pytest.mark.parametrize("proposed", ["成都人民公园", "人民公园（小南街8号）"])
def test_confirmed_place_not_dropped_when_model_adds_city_prefix(proposed):
    identity=uuid4();now=datetime.now(UTC)
    park=Place(ref={"place_id":identity,"external_ref":{"provider_place_id":"fixture"}},name="人民公园",address="小南街8号(地铁站附近)",category="attraction",city="成都市",
        location={"longitude":104,"latitude":30},source={"source_url":"https://fixture.invalid","fetched_at":now,"expires_at":now+timedelta(hours=1)})
    class Places:
        async def get_place(self, place_id, **kwargs):
            assert place_id==identity
            return park
        async def search(self,*args):
            raise AssertionError("verified identity must not be searched again")
    history=[{"user":"人民公园，小南街8号", "place_cards":[{"place":{"place_id":str(identity),"name":"人民公园","address":park.address,"city":"成都市"}}]}]
    value=plan({"item_ref":"park","name":proposed,"duration_minutes":90,"duration_source":"planning_allocation"})
    result=asyncio.run(resolve_plan(value,"成都",SimpleNamespace(service=Places()),history,"只排人民公园"))
    assert result.days[0].items[0].place_id==identity
    assert result.days[0].items[0].name=="人民公园"


def test_decorated_address_cannot_borrow_another_branch_identity():
    from app.conversation_candidate.service import proposed_name_matches
    ref={"name":"人民公园","address":"小南街8号"}
    assert not proposed_name_matches("人民公园（北京路88号）",ref,"成都","北京路88号")
    assert not proposed_name_matches("人民公园（小南街8号）",ref,"成都","去人民公园")


def test_literal_name_and_address_can_resolve_without_prior_consultation():
    from app.place_content.contracts import SearchResponse
    now=datetime.now(UTC);identity=uuid4()
    park=Place(ref={"place_id":identity,"external_ref":{"provider_place_id":"fixture"}},name="人民公园",address="小南街8号",category="attraction",city="成都市",
        location={"longitude":104,"latitude":30},source={"source_url":"https://fixture.invalid","fetched_at":now,"expires_at":now+timedelta(hours=1)})
    class Places:
        async def search(self, query):
            assert query.query=="人民公园" and query.category is None
            return SearchResponse(items=[park],page=1,page_size=12,status="ok")
    value=plan({"item_ref":"park","name":"人民公园（小南街8号）","duration_minutes":90})
    result=asyncio.run(resolve_plan(value,"成都",SimpleNamespace(service=Places()),[],"只去人民公园，小南街8号的那个"))
    assert result.days[0].items[0].place_id==identity
    with pytest.raises(ValueError):
        asyncio.run(resolve_plan(value,"成都",SimpleNamespace(service=Places()),[],"不要去人民公园，小南街8号的那个"))
    with pytest.raises(ValueError):
        asyncio.run(resolve_plan(value,"成都",SimpleNamespace(service=Places()),[],"不去人民公园，小南街8号的那个"))
    with pytest.raises(ValueError):
        asyncio.run(resolve_plan(value,"成都",SimpleNamespace(service=Places()),[],"人民公园只作备选，小南街8号的那个"))


def test_prior_hard_requirement_reaches_preparation_without_selector_repeating_it():
    from app.assistant_context import ContextEnvelope
    from app.assistant_capabilities import CapabilityDecision
    from app.requirements import capture_explicit_requirements
    from app.conversation_candidate.service import build_candidate
    from datetime import date
    message="请创建成都2026-11-09开始、玩1天的安排，10:00出发18:00结束，步行，中午留一小时吃饭"
    value=plan({"item_ref":"lunch","kind":"meal","name":"午餐","start_time":"12:00","end_time":"13:00",
        "duration_minutes":60,"duration_source":"planning_allocation","source_quote":"中午留一小时吃饭"})
    records=capture_explicit_requirements([],"全程不能走台阶",scope={"kind":"topic","topic_id":"test","city":"成都"},source_ref="earlier-message",force=True)
    envelope=ContextEnvelope(topic_id="test",requirement_records=records)
    decision=CapabilityDecision(intent="create",city="成都",reason_code="explicit_write",authorization_quote=message,
        candidate_command={"action":"generate","source_quote":message,"plan":value.model_dump(mode="json")})
    draft,prepared=asyncio.run(build_candidate(decision.candidate_command,decision,message,[],envelope,
        SimpleNamespace(service=SimpleNamespace()),None,today=date(2026,10,24)))
    assert any(r["source"]["ref"]=="earlier-message" and r["strength"]=="hard" for r in draft.requirement_records)
    assert any("全程不能走台阶" in issue for issue in prepared.coverage.blockers)
