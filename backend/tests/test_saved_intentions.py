from datetime import datetime
from zoneinfo import ZoneInfo
from app.saved_intentions import IntentionProposal, validate_proposals
from app.assistant_memory import anchored_date


def test_explicit_intention_requires_current_source_and_preserves_fuzzy_time():
    text = "我明天下午去人民公园，几点再说。"
    proposal = IntentionProposal(place_text="人民公园", source_quote=text, date_text="明天", time_period="下午")
    assert validate_proposals([proposal], text) == [proposal]
    assert anchored_date("明天", datetime(2026, 10, 22, 23, 59, tzinfo=ZoneInfo("Asia/Shanghai")).date()) == "2026-10-23"
    assert not validate_proposals([proposal], "想了解人民公园")
    assert not validate_proposals([proposal.model_copy(update={"place_text": "杜甫草堂"})], text)


def test_questions_hypotheticals_third_party_and_no_save_do_not_write():
    for text in ["如果我明天去人民公园", "朋友说我明天去人民公园", "我明天去人民公园吗？", "记下人民公园，但不要保存", "我不去人民公园了", "人民公园和宽窄巷子哪个更好"]:
        assert not validate_proposals([IntentionProposal(place_text="人民公园", source_quote=text)], text)


def test_selected_place_pronoun_requires_verified_focus_and_dedupes_within_turn():
    p = IntentionProposal(place_text="人民公园", source_quote="记下这里，日期未定")
    assert not validate_proposals([p], p.source_quote)
    assert validate_proposals([p,p], p.source_quote, "人民公园") == [p]


def test_date_and_period_cannot_be_invented():
    p=IntentionProposal(place_text="人民公园",source_quote="记下人民公园，日期未定",date_text="明天",time_period="下午")
    assert not validate_proposals([p],p.source_quote)
