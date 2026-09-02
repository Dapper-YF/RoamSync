import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Activity, DayPlan, PlaceCandidate, SourceRecord, Trip, TripPreferences


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
        "description": "从断桥沿白堤慢行，串联湖景、晨光与杭州城市气质。",
        "longitude": "120.150270", "latitude": "30.260120", "duration": 90,
        "cost": 0, "rating": "4.8", "tags": ["湖景", "步行", "摄影", "免费"],
        "source_title": "西湖风景名胜区", "source_url": "https://www.amap.com/place/B023B0A1UN", "provider": "高德地图",
    },
    {
        "slug": "lingyin",
        "name": "灵隐飞来峰景区",
        "category": "culture",
        "neighborhood": "灵隐路",
        "description": "杭州代表性山林寺院组合，石窟、古刹与林荫步道集中。",
        "longitude": "120.101410", "latitude": "30.240940", "duration": 150,
        "cost": 7500, "rating": "4.7", "tags": ["古建", "山林", "预约", "门票"],
        "source_title": "灵隐飞来峰景区", "source_url": "https://www.amap.com/place/B023B0A6YT", "provider": "高德地图",
    },
    {
        "slug": "longjing",
        "name": "龙井村·九溪入口",
        "category": "nature",
        "neighborhood": "龙井路",
        "description": "茶山、村落与轻徒步组合，适合在午后体验杭州茶文化。",
        "longitude": "120.100680", "latitude": "30.220190", "duration": 120,
        "cost": 3000, "rating": "4.5", "tags": ["茶山", "轻徒步", "摄影"],
        "source_title": "龙井村", "source_url": "https://www.amap.com/place/B023B0A3P9", "provider": "高德地图",
    },
    {
        "slug": "china-art-academy",
        "name": "中国美术学院美术馆",
        "category": "culture",
        "neighborhood": "南山路",
        "description": "湖滨人文节点，也是雨天或高温时可靠的室内替代方案。",
        "longitude": "120.158250", "latitude": "30.247030", "duration": 90,
        "cost": 0, "rating": "4.6", "tags": ["展览", "室内", "预约", "建筑"],
        "source_title": "中国美术学院美术馆", "source_url": "https://www.caa.edu.cn", "provider": "官方网站",
    },
    {
        "slug": "hefang-street",
        "name": "河坊街·南宋御街",
        "category": "shopping",
        "neighborhood": "清河坊",
        "description": "老城夜游节点，适合品尝小吃并完成伴手礼采购。",
        "longitude": "120.174290", "latitude": "30.238520", "duration": 75,
        "cost": 8000, "rating": "4.3", "tags": ["夜游", "小吃", "老街"],
        "source_title": "清河坊历史文化街区", "source_url": "https://www.amap.com/place/B023B0A0FH", "provider": "高德地图",
    },
    {
        "slug": "green-tea",
        "name": "绿茶餐厅·湖滨店",
        "category": "food",
        "neighborhood": "湖滨商圈",
        "description": "衔接湖滨行程的杭帮菜正餐，适合作为首日午餐。",
        "longitude": "120.165880", "latitude": "30.257720", "duration": 70,
        "cost": 9000, "rating": "4.4", "tags": ["杭帮菜", "正餐", "排队"],
        "source_title": "绿茶餐厅", "source_url": "https://www.amap.com/search?id=B0FFG5M5P1", "provider": "高德地图",
    },
    {
        "slug": "leifeng-pagoda",
        "name": "雷峰塔",
        "category": "sight",
        "neighborhood": "南山路",
        "description": "登塔可俯瞰西湖，傍晚光线适合观看湖面与城市天际线。",
        "longitude": "120.148520", "latitude": "30.231110", "duration": 75,
        "cost": 4000, "rating": "4.5", "tags": ["地标", "日落", "门票"],
        "source_title": "雷峰塔景区", "source_url": "https://www.amap.com/place/B023B0A4LM", "provider": "高德地图",
    },
    {
        "slug": "xiaohe-park",
        "name": "小河公园",
        "category": "sight",
        "neighborhood": "拱墅区",
        "description": "运河边工业遗存更新空间，可作为雨天或取消茶山后的备选。",
        "longitude": "120.142360", "latitude": "30.315240", "duration": 80,
        "cost": 0, "rating": "4.6", "tags": ["建筑", "运河", "免费", "备选"],
        "source_title": "小河公园", "source_url": "https://www.amap.com/place/B0H6JMM4T8", "provider": "高德地图",
    },
    {
        "slug": "zhiweiguan",
        "name": "知味观·湖滨总店",
        "category": "food",
        "neighborhood": "湖滨商圈",
        "description": "杭州传统点心与小吃集合，适合早餐、返程前补给或伴手礼采购。",
        "longitude": "120.162530", "latitude": "30.254960", "duration": 60,
        "cost": 6000, "rating": "4.4", "tags": ["老字号", "杭帮点心", "伴手礼"],
        "source_title": "知味观湖滨总店", "source_url": "https://www.amap.com/search?query=%E7%9F%A5%E5%91%B3%E8%A7%82%E6%B9%96%E6%BB%A8%E6%80%BB%E5%BA%97", "provider": "高德地图",
    },
    {
        "slug": "tea-museum",
        "name": "中国茶叶博物馆·双峰馆区",
        "category": "culture",
        "neighborhood": "龙井路",
        "description": "系统了解中国茶文化，与龙井村形成内容连贯的半日路线。",
        "longitude": "120.117200", "latitude": "30.225220", "duration": 90,
        "cost": 0, "rating": "4.7", "tags": ["茶文化", "博物馆", "预约", "免费"],
        "source_title": "中国茶叶博物馆", "source_url": "https://www.teamuseum.cn", "provider": "官方网站",
    },
    {
        "slug": "hangzhou-museum",
        "name": "杭州博物馆",
        "category": "culture",
        "neighborhood": "吴山",
        "description": "从城市历史理解杭州，邻近河坊街，适合替代高温时段的户外项目。",
        "longitude": "120.171080", "latitude": "30.236920", "duration": 90,
        "cost": 0, "rating": "4.7", "tags": ["城市历史", "室内", "预约", "备选"],
        "source_title": "杭州博物馆", "source_url": "https://www.hzmuseum.com", "provider": "官方网站",
    },
    {
        "slug": "tea-lunch",
        "name": "茶人村·龙井路店",
        "category": "food",
        "neighborhood": "龙井路",
        "description": "茶香主题杭帮菜，与灵隐和茶博路线顺路衔接。",
        "longitude": "120.111850", "latitude": "30.229780", "duration": 75,
        "cost": 8500, "rating": "4.5", "tags": ["杭帮菜", "茶餐", "正餐"],
        "source_title": "龙井路餐饮检索", "source_url": "https://www.amap.com/search?query=%E8%8C%B6%E4%BA%BA%E6%9D%91", "provider": "高德地图",
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
        title="杭州两日一夜 · 湖山人文之旅",
        destination="杭州",
        destination_adcode="330100",
        destination_citycode="0571",
        center_longitude=Decimal("120.155070"),
        center_latitude=Decimal("30.274085"),
        accommodation="杭州君悦酒店",
        accommodation_poi_id="B023B02FMY",
        accommodation_address="湖滨路28号（龙翔桥地铁站出入口步行约430米）",
        accommodation_district="上城区",
        accommodation_longitude=Decimal("120.161532"),
        accommodation_latitude=Decimal("30.254794"),
        start_date=date(2026, 9, 5),
        end_date=date(2026, 9, 6),
        total_budget_fen=420_000,
        daily_budget_fen=100_000,
        currency="CNY",
        timezone="Asia/Shanghai",
    )
    session.add(trip)
    await session.flush()
    session.add(
        TripPreferences(
            trip_id=DEMO_TRIP_ID,
            pace="balanced",
            interest_categories=["history", "culture", "nature", "food", "photography"],
            transport_modes=["walk", "transit"],
            daily_start_time=time(8, 30),
            daily_end_time=time(21, 30),
            meal_preferences="偏好杭帮菜与本地老字号；午餐可排队，晚餐希望轻松且靠近住宿。",
            avoid_categories=["连续长距离步行", "大型购物中心"],
            max_walking_minutes=50,
            free_text_requirements="首次到杭州，希望覆盖西湖经典景观、人文艺术、灵隐与龙井茶文化；每天保留休息和交通缓冲，第二天下午不宜太赶。",
        )
    )

    queried_at = datetime(2026, 9, 2, 2, 0, tzinfo=UTC)
    places: dict[str, PlaceCandidate] = {}
    sources: list[SourceRecord] = []
    place_records: list[PlaceCandidate] = []
    for item in PLACE_DATA:
        slug = str(item["slug"])
        source = SourceRecord(
            id=demo_uuid("source", slug), trip_id=DEMO_TRIP_ID,
            title=str(item["source_title"]), url=str(item["source_url"]),
            provider=str(item["provider"]), queried_at=queried_at, confidence="high",
        )
        place = PlaceCandidate(
            id=demo_uuid("place", slug), trip_id=DEMO_TRIP_ID, source_record_id=source.id,
            slug=slug, name=str(item["name"]), category=str(item["category"]),
            neighborhood=str(item["neighborhood"]), description=str(item["description"]),
            longitude=Decimal(str(item["longitude"])), latitude=Decimal(str(item["latitude"])),
            suggested_duration_minutes=int(item["duration"]), estimated_cost_fen=int(item["cost"]),
            rating=Decimal(str(item["rating"])), tags=list(item["tags"]),
        )
        sources.append(source)
        place_records.append(place)
        places[slug] = place

    session.add_all(sources)
    await session.flush()
    session.add_all(place_records)
    await session.flush()

    day_one = DayPlan(
        id=demo_uuid("day", "day-1"), trip_id=DEMO_TRIP_ID, date=date(2026, 9, 5),
        label="第 1 天", theme="湖滨美学、杭帮味道与南宋夜色", position=0, route_mode="walk",
    )
    day_two = DayPlan(
        id=demo_uuid("day", "day-2"), trip_id=DEMO_TRIP_ID, date=date(2026, 9, 6),
        label="第 2 天", theme="灵隐禅意、龙井茶山与从容返程", position=1, route_mode="walk",
    )
    session.add_all([day_one, day_two])
    await session.flush()

    initial_activities = [
        (day_one, "west-lake", time(9, 0), 0, "从酒店步行到湖边。断桥后沿白堤慢行；11:15在湖滨安排杭帮菜午餐，雨天可缩短至60分钟。"),
        (day_one, "china-art-academy", time(13, 0), 1, "提前查看当期展览与预约规则；携带身份证。参观后沿南山路看雷峰塔日落。"),
        (day_one, "hefang-street", time(18, 0), 2, "晚餐与伴手礼预算合并估算。串联南宋御街，游览后返回湖滨酒店。"),
        (day_two, "lingyin", time(8, 30), 0, "7:45从酒店出发并完成飞来峰预约；11:40在龙井路午餐，避开午后客流高峰。"),
        (day_two, "longjing", time(13, 20), 1, "先参观中国茶叶博物馆，再进入龙井村轻徒步；17:30前返程，不安排强制购物。"),
    ]
    for day, slug, scheduled_time, position, note in initial_activities:
        place = places[slug]
        session.add(
            Activity(
                id=demo_uuid("activity", slug), day_plan_id=day.id, place_candidate_id=place.id,
                scheduled_time=scheduled_time, duration_minutes=place.suggested_duration_minutes,
                estimated_cost_fen=place.estimated_cost_fen, status="planned", position=position,
                schedule_locked=False, note=note,
            )
        )

    await session.flush()
    from app.maps_service import recalculate_day_route

    await recalculate_day_route(session, day_one.id)
    await recalculate_day_route(session, day_two.id)
    await session.commit()
    return True
