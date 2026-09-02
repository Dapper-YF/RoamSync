import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Activity, DayPlan, PlaceCandidate, SourceRecord, Trip


DEMO_TRIP_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEMO_NAMESPACE = uuid.UUID("f680b8be-1312-4fe4-8b4e-13613e5a024c")


def demo_uuid(kind: str, slug: str) -> uuid.UUID:
    return uuid.uuid5(DEMO_NAMESPACE, f"{kind}:{slug}")


PLACE_DATA = [
    {
        "slug": "west-lake",
        "name": "西湖·断桥",
        "category": "nature",
        "neighborhood": "北山街",
        "description": "从断桥开始沿湖慢行，适合作为第一天的低强度开场。",
        "longitude": "120.150270",
        "latitude": "30.260120",
        "duration": 90,
        "cost": 0,
        "rating": "4.8",
        "tags": ["湖景", "步行", "免费"],
        "source_title": "西湖风景名胜区",
        "source_url": "https://www.amap.com/place/B023B0A1UN",
        "provider": "高德地图",
    },
    {
        "slug": "lingyin",
        "name": "灵隐寺",
        "category": "culture",
        "neighborhood": "灵隐路",
        "description": "山林寺院组合，建议预留半天并避开午后返程高峰。",
        "longitude": "120.101410",
        "latitude": "30.240940",
        "duration": 150,
        "cost": 7500,
        "rating": "4.7",
        "tags": ["古建", "山林", "门票"],
        "source_title": "灵隐景区",
        "source_url": "https://www.amap.com/place/B023B0A6YT",
        "provider": "高德地图",
    },
    {
        "slug": "longjing",
        "name": "龙井村",
        "category": "nature",
        "neighborhood": "龙井路",
        "description": "茶山与村落路线，适合天气晴朗时安排在上午。",
        "longitude": "120.100680",
        "latitude": "30.220190",
        "duration": 120,
        "cost": 3000,
        "rating": "4.5",
        "tags": ["茶山", "轻徒步", "拍照"],
        "source_title": "龙井村",
        "source_url": "https://www.amap.com/place/B023B0A3P9",
        "provider": "高德地图",
    },
    {
        "slug": "china-art-academy",
        "name": "中国美术学院美术馆",
        "category": "culture",
        "neighborhood": "南山路",
        "description": "靠近湖滨，作为雨天或高温时的室内替代节点。",
        "longitude": "120.158250",
        "latitude": "30.247030",
        "duration": 90,
        "cost": 0,
        "rating": "4.6",
        "tags": ["展览", "室内", "预约"],
        "source_title": "中国美术学院美术馆",
        "source_url": "https://www.caa.edu.cn",
        "provider": "官方网站",
    },
    {
        "slug": "hefang-street",
        "name": "河坊街",
        "category": "shopping",
        "neighborhood": "清河坊",
        "description": "老街夜游节点，餐饮与购物花费弹性较大。",
        "longitude": "120.174290",
        "latitude": "30.238520",
        "duration": 75,
        "cost": 8000,
        "rating": "4.3",
        "tags": ["夜游", "小吃", "老街"],
        "source_title": "清河坊历史文化街区",
        "source_url": "https://www.amap.com/place/B023B0A0FH",
        "provider": "高德地图",
    },
    {
        "slug": "green-tea",
        "name": "绿茶餐厅·湖滨店",
        "category": "food",
        "neighborhood": "湖滨商圈",
        "description": "方便衔接湖滨行程的正餐候选，演示预算预估用途。",
        "longitude": "120.165880",
        "latitude": "30.257720",
        "duration": 70,
        "cost": 9000,
        "rating": "4.4",
        "tags": ["杭帮菜", "正餐", "排队"],
        "source_title": "绿茶餐厅",
        "source_url": "https://www.amap.com/search?id=B0FFG5M5P1",
        "provider": "高德地图",
    },
    {
        "slug": "leifeng-pagoda",
        "name": "雷峰塔",
        "category": "sight",
        "neighborhood": "南山路",
        "description": "可俯瞰西湖，适合在日落前到达。",
        "longitude": "120.148520",
        "latitude": "30.231110",
        "duration": 75,
        "cost": 4000,
        "rating": "4.5",
        "tags": ["地标", "日落", "门票"],
        "source_title": "雷峰塔景区",
        "source_url": "https://www.amap.com/place/B023B0A4LM",
        "provider": "高德地图",
    },
    {
        "slug": "xiaohe-park",
        "name": "小河公园",
        "category": "sight",
        "neighborhood": "拱墅区",
        "description": "运河边工业遗存更新空间，适合第二天下午慢行。",
        "longitude": "120.142360",
        "latitude": "30.315240",
        "duration": 80,
        "cost": 0,
        "rating": "4.6",
        "tags": ["建筑", "运河", "免费"],
        "source_title": "小河公园",
        "source_url": "https://www.amap.com/place/B0H6JMM4T8",
        "provider": "高德地图",
    },
]


async def seed_demo_data(session: AsyncSession, *, reset: bool = False) -> bool:
    existing = await session.get(Trip, DEMO_TRIP_ID)
    if existing is not None and not reset:
        return False
    if existing is not None:
        await session.execute(delete(Trip).where(Trip.id == DEMO_TRIP_ID))
        await session.flush()

    trip = Trip(
        id=DEMO_TRIP_ID,
        title="杭州 · 两日慢游",
        destination="杭州",
        accommodation="杭州湖滨银泰附近",
        start_date=date(2026, 9, 5),
        end_date=date(2026, 9, 6),
        total_budget_fen=120_000,
        daily_budget_fen=60_000,
        currency="CNY",
        timezone="Asia/Shanghai",
    )
    session.add(trip)
    await session.flush()

    queried_at = datetime(2026, 8, 31, 2, 0, tzinfo=UTC)
    places: dict[str, PlaceCandidate] = {}
    sources: list[SourceRecord] = []
    place_records: list[PlaceCandidate] = []
    for item in PLACE_DATA:
        slug = str(item["slug"])
        source = SourceRecord(
            id=demo_uuid("source", slug),
            trip_id=DEMO_TRIP_ID,
            title=str(item["source_title"]),
            url=str(item["source_url"]),
            provider=str(item["provider"]),
            queried_at=queried_at,
            confidence="high",
        )
        place = PlaceCandidate(
            id=demo_uuid("place", slug),
            trip_id=DEMO_TRIP_ID,
            source_record_id=source.id,
            slug=slug,
            name=str(item["name"]),
            category=str(item["category"]),
            neighborhood=str(item["neighborhood"]),
            description=str(item["description"]),
            longitude=Decimal(str(item["longitude"])),
            latitude=Decimal(str(item["latitude"])),
            suggested_duration_minutes=int(item["duration"]),
            estimated_cost_fen=int(item["cost"]),
            rating=Decimal(str(item["rating"])),
            tags=list(item["tags"]),
        )
        sources.append(source)
        place_records.append(place)
        places[slug] = place

    session.add_all(sources)
    await session.flush()
    session.add_all(place_records)
    await session.flush()

    day_one = DayPlan(
        id=demo_uuid("day", "day-1"),
        trip_id=DEMO_TRIP_ID,
        date=date(2026, 9, 5),
        label="第 1 天",
        theme="湖滨散步与城市夜色",
        position=0,
    )
    day_two = DayPlan(
        id=demo_uuid("day", "day-2"),
        trip_id=DEMO_TRIP_ID,
        date=date(2026, 9, 6),
        label="第 2 天",
        theme="山林茶村与从容返程",
        position=1,
    )
    session.add_all([day_one, day_two])
    await session.flush()

    initial_activities = [
        (day_one, "west-lake", time(9, 30), 0),
        (day_one, "china-art-academy", time(13, 30), 1),
        (day_one, "hefang-street", time(18, 20), 2),
        (day_two, "lingyin", time(8, 40), 0),
        (day_two, "longjing", time(13, 20), 1),
    ]
    for day, slug, scheduled_time, position in initial_activities:
        place = places[slug]
        session.add(
            Activity(
                id=demo_uuid("activity", slug),
                day_plan_id=day.id,
                place_candidate_id=place.id,
                scheduled_time=scheduled_time,
                duration_minutes=place.suggested_duration_minutes,
                estimated_cost_fen=place.estimated_cost_fen,
                status="planned",
                position=position,
            )
        )

    await session.flush()
    from app.maps_service import recalculate_day_route

    await recalculate_day_route(session, day_one.id)
    await recalculate_day_route(session, day_two.id)
    await session.commit()
    return True
