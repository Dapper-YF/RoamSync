import asyncio
from dataclasses import replace
from datetime import time

from app.saved_trip_reads import load_saved_trip_read, render_saved_request
from test_b3_saved_trip_reads import sessions, seed


def test_saved_ordinal_matches_chronological_handbook_even_after_position_changes(sessions):
    async def run():
        async with sessions() as db:
            trip, days, activities = await seed(db)
            activities[1].scheduled_time = time(8)
            await db.commit()
            snapshot = await load_saved_trip_read(db, trip.id)
            projection = snapshot.project('第一天第一项活动')
            assert projection['activities'][0]['activity_id'] == str(activities[1].id)
    asyncio.run(run())


def test_saved_first_item_does_not_hide_same_day_other_activities(sessions):
    async def run():
        async with sessions() as db:
            trip, days, activities = await seed(db)
            snapshot = await load_saved_trip_read(db, trip.id)
            text = render_saved_request(snapshot, '总天数、第一天第一项活动、第一天其他活动和最后一天留白')
            assert '共3天' in text and '合成地点1，' in text
            assert '合成地点2，' in text and '合成地点5，' in text
            assert '午餐留白' in text
            assert '合成地点6，' not in text
            assert '合成地点11，' not in text  # requested only last-day free intervals
    asyncio.run(run())


def test_bare_item_does_not_silently_count_past_a_free_window(sessions):
    async def run():
        async with sessions() as db:
            trip, days, activities = await seed(db)
            snapshot = await load_saved_trip_read(db, trip.id)
            assert snapshot.project('第三天第四项')['coverage']['ambiguous']
            explicit = snapshot.project('第三天第四项活动')
            assert not explicit['coverage']['ambiguous']
            assert explicit['activities'][0]['activity_id'] == str(activities[13].id)
    asyncio.run(run())


def test_read_goals_respect_denial_whole_trip_and_partial_agenda(sessions):
    async def run():
        async with sessions() as db:
            trip, days, activities = await seed(db)
            snapshot = await load_saved_trip_read(db, trip.id)
            text = render_saved_request(snapshot, '不看第一天，只看第二天活动')
            assert '合成地点1，' not in text and '合成地点6，' in text
            text = render_saved_request(snapshot, '第一天午餐和全程所有活动')
            assert '合成地点1，' in text and '合成地点11，' in text
            assert snapshot.project('第一天第一项到第三项')['coverage']['ambiguous']
            incomplete = replace(snapshot, items=(), item_count=1)
            assert incomplete.project('第一天第一项')['coverage']['ambiguous']
            assert not incomplete.project('第一天第一项活动')['coverage']['ambiguous']
            text = render_saved_request(snapshot, '第三天午餐留白、第三天午餐留白')
            assert text.count('午餐留白') == 1 and '没有保存' not in text
            assert '合成地点1，' not in render_saved_request(snapshot, '不看第一天')
            assert '共3天' not in render_saved_request(snapshot, '不读总天数')
            text = render_saved_request(snapshot, '第一天活动、全程所有活动、午餐')
            assert '午餐留白' in text
    asyncio.run(run())
