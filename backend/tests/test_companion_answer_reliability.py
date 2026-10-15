import asyncio
import json
from pathlib import Path
import pytest

from app.companion_answer_reliability import control_model_text, live_gap_text, source_gap_text
from app.companion_contracts import CompanionDraft, SuggestionDraft
from app.companion_provider import CompanionProviderError
from app.companion_runtime import CompanionRuntime
from app.travel_goal_router import route_travel_goal
from evals.companion_knowledge_strategy import Reader


@pytest.mark.parametrize('text,code', [
    ('园林讲究借景，茶位费几元一杯，可以观察窗景。', 'price'),
    ('通常门票30元。', 'price'),
    ('巷子几乎不用排队，可以慢慢看建筑。', 'queue'),
    ('下午场多是本地老听客。', 'operation'),
    ('这里行人少，适合观察建筑。', 'crowding'),
    ('一定安静。', 'crowding'),
    ('比拙政园清静得多。', 'crowding'),
    ('比前段商业区安静许多。', 'crowding'),
    ('小巷人也少。', 'crowding'),
    ('茶馆氛围安静。', 'crowding'),
    ('清晨尤其安静。', 'crowding'),
    ('两侧小巷基本没什么人。', 'crowding'),
    ('几乎不需要排队。', 'queue'),
    ('预约名额紧张。', 'availability'),
    ('明天正常营业。', 'operation'),
    ('博物馆偶有演出。', 'operation'),
    ('还有预约名额。', 'availability'),
])
def test_unsupported_state_clauses(text, code):
    result = control_model_text(text, '想慢慢旅行')
    assert 'output_unverified_' + code in result.issues
    assert not any(word in result.text for word in ['30元', '几元', '几乎不用排队', '行人少', '一定安静', '正常营业', '还有预约名额'])


@pytest.mark.parametrize('text', [
    '六朝指东吴、东晋、宋、齐、梁、陈。',
    '如果现场拥挤，可以换一条街巷；不能保证免排队。',
    '喜欢安静的话，可以先选择步行范围较小的片区。',
    '每天只安排两个体验，预留100元作为支出上限。',
    '宋代城市文化与园林意境值得讨论。',
    '请查看官方页面确认预约名额。',
])
def test_culture_conditions_and_budget_survive(text):
    result = control_model_text(text, '旅行建议')
    assert result.text == text and not result.issues


def test_relevant_gaps_and_no_unsolicited_photo():
    text = live_gap_text('明天还有预约名额吗')
    assert '预约' in text and all(x not in text for x in ['天气', '票价', '交通'])
    assert '小型知识库' not in source_gap_text('南京文献来源')
    from app.companion_provider import GENERAL_KNOWLEDGE_INSTRUCTIONS
    assert 'Do not add photography tips' in GENERAL_KNOWLEDGE_INSTRUCTIONS
    assert '拍照' in control_model_text('可以拍照。', '怎么拍照').text


def test_removed_list_clause_preserves_paragraph_boundaries():
    text = '1. 观察窗景，几乎不需要排队。\n\n2. 了解借景。'
    result = control_model_text(text, '文化体验')
    assert '\n\n2.' in result.text
    assert '观察窗景' in result.text and '了解借景' in result.text


class Provider:
    def __init__(self, response=None, filtered=False):
        self.response, self.filtered, self.calls = response, filtered, 0
    async def generate(self, context, need):
        self.calls += 1
        if self.filtered:
            raise CompanionProviderError('incomplete', finish_reason='sensitive')
        return self.response


def run(text, provider, history=None):
    return asyncio.run(CompanionRuntime(Reader(), provider).run(
        session_id='reliability-test', turn_id='turn', message=text,
        goal=route_travel_goal(text, history or []), messages=history or []))


def test_mixed_answer_and_saved_suggestion_both_controlled():
    provider = Provider(CompanionDraft(response_text='园林借景值得观察。门票30元。', suggestions=[
        SuggestionDraft(suggestion_type='experience', title='观察园林', summary='留意窗景。这里人少。', reasons=['几乎不用排队。', '可以观察借景。'])]))
    result = run('苏州有哪些文化体验？', provider)
    assert result.response_text == '园林借景值得观察。'
    assert result.suggestions[0].summary == '留意窗景。'
    assert result.suggestions[0].reasons == ['可以观察借景。']
    assert result.status == 'completed' and provider.calls == 1
    assert 'output_unverified_price' in result.claim_validation_issues


def test_filtered_provider_is_needs_information_without_retry():
    provider = Provider(filtered=True)
    result = run('一个人旅游有什么建议？', provider)
    assert result.status == 'needs_information' and provider.calls == 1
    assert 'provider_filtered' in result.claim_validation_issues
    assert not result.suggestions and not result.answer_evidence_refs


def test_live_and_original_rationale_do_not_generate():
    provider = Provider(filtered=True)
    assert '价格' in run('南京现在门票多少钱？', provider).response_text
    assert run('为什么当前行程把西湖安排在18点？', provider).explanation.explanation_type == 'rationale_unavailable'
    assert provider.calls == 0
    assert route_travel_goal('帮我规划南京三天行程').target_runtime == 'planning'


def test_original_failure_replay_and_explicit_historical_limit():
    path = Path(__file__).parents[1] / 'evals/fixtures/companion_answer_reliability_failures.json'
    rows = json.loads(path.read_text(encoding='utf-8'))
    for row in rows:
        result = control_model_text(row['answer'], row['input'])
        if row['blind_id'] in {'Q021', 'Q035', 'Q044'}:
            assert result.issues and result.text
    # State control deliberately cannot validate relationships between historical entities.
    result = control_model_text('白居易留下了白堤。', '杭州文化')
    assert result.text == '白居易留下了白堤。' and not result.issues
