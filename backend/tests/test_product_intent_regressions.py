"""Regression evidence from the isolated 2026-10-16 product execution flow."""
import pytest
from app.planning_intent_service import _extract_place_queries
@pytest.mark.parametrize('message',['不添加新地点','不要增加新活动','无需添加新地点','不必加入新地点','别添加新地点'])
def test_negative_addition_is_not_a_place_request(message):
 assert _extract_place_queries(message)==[]
def test_real_addition_after_negative_clause_is_preserved():
 assert _extract_place_queries('不添加新地点。加入人民公园')==['人民公园']
 assert _extract_place_queries('添加人民公园')==['人民公园']
