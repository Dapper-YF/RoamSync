import asyncio
import pytest
from app.companion_contracts import CompanionContext, CompanionAnswerDraft
from app.companion_information import determine_information_need
from app.travel_goal_router import route_travel_goal
from app.companion_runtime import CompanionRuntime
from app.companion_knowledge import build_reviewed_knowledge_tool
from evals.companion_phase2.run import Reader, CountingTool

class NoModel:
    async def generate(self,context,need):
        raise AssertionError('Mixed stable/live must use server facts and a limitation only')


def test_explicit_nanjing_knowledge_cannot_use_hangzhou_corpus():
    async def run():
        text = '请根据可靠资料介绍南京的历史文化和老街巷；如果资料不足就说明，不要猜。'
        tool = CountingTool(await build_reviewed_knowledge_tool())
        result = await CompanionRuntime(Reader(), NoModel(), tool).run(
            session_id='nanjing-scope', turn_id='current', message=text,
            goal=route_travel_goal(text), messages=[])
        assert tool.calls[0].destination == '南京'
        assert not result.knowledge_evidence
        assert not any(c.claim_type == 'retrieved_fact' for c in result.claims)
        assert '西湖' not in result.response_text
        assert result.information_gaps
    asyncio.run(run())

@pytest.mark.parametrize('text',[
    '请用资料解释西湖的文化背景，明天下午天气也能确认吗？',
    '西湖有哪些景观构成？按出处回答，并说明今天关门时间是否知道。',
    '杭州茶馆的生活体验是什么？给来源，也核实一下今晚的价格。',
])
def test_stable_live_parts_keep_evidence_without_model_guess(text):
    async def run():
        tool=CountingTool(await build_reviewed_knowledge_tool())
        result=await CompanionRuntime(Reader(),NoModel(),tool).run(session_id='coverage',turn_id='mixed',message=text,goal=route_travel_goal(text),messages=[])
        assert result.information_need.live_fact_required and result.information_need.knowledge_required
        assert tool.calls and result.claims
        assert '实时部分目前无法核实' in result.response_text
        assert result.grounding_status=='live_verification_required'
        assert not any(x in result.response_text for x in ['knowledge_','claim_type','资料支持：'])
        assert not any(x in tool.calls[0].query for x in ['今天','明天','今晚','价格','关门'])
    asyncio.run(run())

@pytest.mark.parametrize('text', ['请按资料告诉我现在西湖几点关门', '今天形成什么天气？', '今晚还能买到门票吗？'])
def test_live_only_does_not_acquire_stable_retrieval(text):
    need=determine_information_need(CompanionContext(current_message=text,travel_goal=route_travel_goal(text)),[])
    assert need.live_fact_required and not need.knowledge_required

def test_existing_visit_assertion_is_selected_for_duration_topic():
    async def run():
        from evals.phase25_final import NeutralProvider
        text='按老年旅游规范，连续游览多久需要休息？'
        result=await CompanionRuntime(Reader(),NeutralProvider(),await build_reviewed_knowledge_tool()).run(session_id='coverage',turn_id='visit',message=text,goal=route_travel_goal(text),messages=[])
        assert any('senior.continuous_visit_time' in c.assertion_ids for c in result.claims)
    asyncio.run(run())
