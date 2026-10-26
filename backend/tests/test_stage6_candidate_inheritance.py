from datetime import time

import pytest

from app.conversation_candidate.schedule_evidence import daily_window_source

HISTORY=[{'user':'请生成南京21/11/2026出发的一日候选，去玄武湖和鸡鸣寺，10:00—18:00游玩，中午留一小时午餐，步行为主。先看方案再决定，不要保存。'}]
MESSAGE='玄武湖选玄武湖景区，地址玄武门路1号钟山风景名胜区西侧；鸡鸣寺选鸡鸣寺路1号的鸡鸣寺。请沿用上一条全部日期、10:00—18:00、一小时午餐和步行要求，生成候选给我看，仍不保存。'


def test_repeated_bounds_in_an_inherited_condition_are_the_same_window_source():
    assert daily_window_source(MESSAGE,time(10),time(18),HISTORY)


@pytest.mark.parametrize('message',[
    '不要沿用上一条10:00—18:00时间要求，重新生成候选',
    '如果沿用上一条10:00—18:00时间要求会怎样',
    '请沿用上一条要求，鸡鸣寺10:00—18:00开放',
    '请沿用上一条全部日期、11:00—18:00、一小时午餐和步行要求',
    '请沿用上一条10:00—18:00时间要求，鸡鸣寺15:00预约',
    '沿用之前的时间10:00—18:00作为甲馆参观时段',
])
def test_inheritance_does_not_turn_other_clocks_or_denials_into_daily_bounds(message):
    assert not daily_window_source(message,time(10),time(18),HISTORY)


def test_inheritance_requires_a_prior_valid_window_and_obeys_its_withdrawal():
    assert not daily_window_source(MESSAGE,time(10),time(18),[])
    assert not daily_window_source(MESSAGE,time(10),time(18),[*HISTORY,{'user':'游玩时间待定'}])
