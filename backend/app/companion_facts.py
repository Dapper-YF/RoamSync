"""Thin forecast composition: typed requirements/results; no model weather guesses."""
import asyncio
import math
import re
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Protocol, Sequence
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

from pydantic import BaseModel, Field
from app.travel_facts.models import (FactRequirement, FactType, PlaceSubject, DestinationSubject,
    GeoPoint, LocationValue, ResolvedFact, TimeScope, FactBundle)
from app.travel_facts.interfaces import ProviderUnavailable
from app.travel_facts.policies import FactFreshnessPolicy, FactAuthorityPolicy, FreshnessRule, AuthorityRule
from app.travel_facts.repository import InMemoryFactRepository
from app.travel_facts.normalization import evidence_record, fact_record
from app.travel_facts.service import TravelFactService
from app.travel_facts.adapters import WeatherForecastAdapter, _weather_gateway
from app.travel_facts.opening_hours import OfficialOpeningHoursAdapter, VENUES, official_gateway
from app.forecast_location_extraction import extract_forecast_city_mentions

FORECAST_TTL = 900
DAYPARTS = {"上午": (6,12), "早上": (6,12), "下午": (12,18), "晚上": (18,24), "傍晚": (18,24)}

def city_parts(name: str) -> tuple[str, str]:
    """Separate an explicit province qualifier; never supply a city identity."""
    match = re.fullmatch(r"(.{2,12}?省)(.{2,12})", name)
    province, city = (match[1][:-1], match[2]) if match else ("", name)
    return city[:-1] if city.endswith("市") and len(city) > 2 else city, province


def forecast_location_mentions(text: str, *, statement: bool = False) -> list[str]:
    """Extract user-written search terms, which must still pass geocoding.

    No city catalogue or coordinates live here. Unknown explicit terms must
    not acquire a previous conversation's city when provider lookup fails.
    """
    mentions = []
    for clause in re.split(r"[，,。？！?!；;\n]", text):
        clause = clause.strip()
        if not clause:
            continue
        if not forecast_intent(clause) and not re.search(r"今天|明天|后天", clause):
            if not statement or not re.search(r"(?:去|在|到|目的地是)", clause):
                continue
        value = re.sub(r"(?:\d{4}年)?\d{1,2}月\d{1,2}[日号]|今天|明天|后天|上午|早上|下午|晚上|傍晚|全天|逐小时|每小时|按小时|详细|具体", "", clause)
        value = re.split(r"天气|下雨|降雨|气温|温度|多少度|预报", value, maxsplit=1)[0]
        value = re.sub(r"^(?:(?:所以|那么|那|你好|请问|麻烦|请|帮我|给我|查一下|查查|查询|看看|看一下|我想问一下|我想问|想知道|我想知道|我准备|我打算|我计划|准备|打算|计划|我要|我想|我|是在|在|去|到|目的地是)\s*)+", "", value)
        value = re.sub(r"(?:的|这边|那边|附近|会不会|是否|是不是|有没有|会|可能|要|有|怎么样|如何|呢|吗|吧|旅游|旅行)+$", "", value).strip()
        if value in {"这里", "那里", "这儿", "那儿", "当地", "这个城市", "哪个城市", "一个人", "我们"}:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]{2,24}", value):
            mentions.append(value)
    return list(dict.fromkeys(mentions))

class ForecastPlan(BaseModel):
    requirements: list[FactRequirement] = Field(default_factory=list, max_length=24)
    place_result: ResolvedFact | None = None
    location_label: str = ""
    timezone: str | None = None
    message: str = ""
    clarification: bool = False

class FactToolPort(Protocol):
    async def plan_forecast(self, text: str, destination: str | None, recent_turns: list[dict]) -> ForecastPlan: ...
    async def resolve_facts(self, requirements: Sequence[FactRequirement]) -> Sequence[ResolvedFact]: ...
    async def plan_opening_hours(self, text: str, recent_turns: list[dict]) -> ForecastPlan: ...

def opening_intent(text):
    return bool(re.search(r"开门|关门|开馆|闭馆|闭园|开着|开吗|几点开|几点关|开放|营业|还能进去|能进馆",text))

def opening_text(plan, results):
    if plan.message: return plan.message
    hours=[r for r in results if r.requirement.fact_type==FactType.OPENING_HOURS]
    if any(r.resolution_status=="conflicting" for r in hours): return "我查到的开放时间信息存在冲突，目前不能确认一个可靠时间。"
    good=[r for r in hours if r.usable_as_current and r.resolution_status=="resolved" and r.freshness_status=="fresh"]
    if not good: return "我目前没有取得适用于这个日期的可靠开放公告，不能确认目标日时间；常规周营业表也不能排除节假日调整或临时闭馆。"
    r=good[0]; v=r.value; source=r.selected_evidence[0]
    row="公告安排为全天闭馆" if v.closed_all_day else "公告开放时段为"+"、".join(f"{x.start:%H:%M}–{x.end:%H:%M}" for x in v.intervals)
    if v.last_admission: row+=f"，{v.last_admission:%H:%M}停止入馆"
    return (f"{plan.location_label}，{v.local_date}（{v.timezone}）：{row}。\n"
        f"依据场馆官方日期公告（{source.metadata['publication_time']}发布），本次{source.retrieved_at.astimezone(ZoneInfo(v.timezone)):%m月%d日 %H:%M}获取。"
        f"\n{source.source_reference}\n这是已发布的日期安排，不能证明此刻实际开着，也不保证能入馆；未确认不存在临时调整，具体展厅可能另有安排。")

def forecast_intent(text):
    return bool(re.search(r"天气|下雨|降雨|气温|多少度|温度", text))

def time_window(text: str, timezone: str, now: datetime):
    """Deterministic local future whole hours; end exclusive, no past observation."""
    local = now.astimezone(ZoneInfo(timezone))
    if re.search(r"现在|此刻|当前|实时|刚才|昨天|前天|预警|警报",text):
        return None, "我目前只支持未来小时预报，不能核实当前实测天气、过去天气或气象预警。", False
    relative=re.findall(r"今天|明天|后天",text)
    explicit=re.findall(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})[日号]",text)
    if len(set(relative))+len(explicit)!=1:
        return None, "你想看哪一天的天气预报？请给出一个明确日期。", True
    try:
        if explicit:
            year,month,day=explicit[0]
            target=local.date().replace(year=int(year) if year else local.year,month=int(month),day=int(day))
        else:
            target=local.date()+timedelta(days={"今天":0,"明天":1,"后天":2}[relative[0]])
    except ValueError:
        return None,"这个日期无法确认，请给出有效的年月日。",True
    if target<local.date() or target>local.date()+timedelta(days=6):
        return None,"我目前只支持当地今天至未来六天的小时预报，不能用预报回答过去实测天气或更远日期。",False
    parts=[p for p in DAYPARTS if p in text]
    if len(parts)>1 or re.search(r"\d{1,2}(?:点|时|[:：])",text):
        return None,"请指定上午、下午、晚上或全天；本轮还不支持任意钟点或多个时段的解析。",True
    first,last=DAYPARTS[parts[0]] if parts else (0,24)
    start=datetime.combine(target,datetime.min.time(),tzinfo=ZoneInfo(timezone))+timedelta(hours=first)
    end=datetime.combine(target,datetime.min.time(),tzinfo=ZoneInfo(timezone))+timedelta(hours=last)
    while start<=local:
        start+=timedelta(hours=1)
    if start>=end:
        return None,"这个时段已过去，我不能把历史或当前实测当成未来预报。",False
    return (start,end),"",False

async def geocode_gateway(name):
    from app.config import get_settings
    from app.external_facts import _get_json
    url="https://geocoding-api.open-meteo.com/v1/search?"+urlencode(dict(name=name,count=10,language="zh",countryCode="CN"))
    return await asyncio.to_thread(_get_json,url,timeout=get_settings().weather_timeout_seconds)

class CityLocationAdapter:
    name, read_through = "open_meteo_geocoding", False
    def __init__(self, freshness, gateway=geocode_gateway, clock=lambda: datetime.now(UTC)):
        self.freshness,self.gateway,self.clock=freshness,gateway,clock
    def supports(self,req):
        return (req.fact_type == FactType.PLACE_LOCATION and isinstance(req.subject, PlaceSubject)
            and req.subject.ref.startswith("city-search:") and bool(req.subject.name))
    async def fetch(self,req,*,now):
        query,admin=city_parts(req.subject.name)
        payload=await self.gateway(query)
        matches=[x for x in payload.get("results",[]) if city_parts(str(x.get("name", "")))[0]==query and
            x.get("country_code")=="CN" and x.get("feature_code") in {"PPLA","PPLC","PPLA2","PPLA3"}
            and (not admin or admin == re.sub(r"省$", "", x.get("admin1", "")))]
        if not matches or len({x.get("id") for x in matches}) != len(matches):
            return FactBundle()
        facts, evidence_rows = [], []
        for item in matches:
            ZoneInfo(item["timezone"])
            value=LocationValue(point=GeoPoint(latitude=item["latitude"],longitude=item["longitude"],coordinate_system="wgs84"))
            evidence=evidence_record(provider=self.name,source_type="structured_api",source_reference="geonames:"+str(item["id"]),
                retrieved_at=self.clock(),normalized_snapshot={"name":item["name"],"value":value.model_dump(mode="json")},
                metadata={"timezone":item["timezone"],"geonames_id":str(item["id"]),"scope":"representative_city_location",
                    "city_name":item["name"],"admin1":item.get("admin1", "")},raw_payload=payload)
            facts.append(fact_record(fact_type=req.fact_type,subject=req.subject,value=value,evidence=evidence,freshness=self.freshness,nature="provider_assertion"))
            evidence_rows.append(evidence)
        return FactBundle(facts=tuple(facts),evidence=tuple(evidence_rows))

class CompanionFactAdapter:
    def __init__(self, *, geocoder=geocode_gateway, weather_gateway=_weather_gateway, opening_gateway=official_gateway,
                 clock=lambda:datetime.now(UTC), location_extractor=extract_forecast_city_mentions):
        self.clock,self.weather_gateway=clock,weather_gateway
        self.location_extractor=location_extractor
        self.opening_gateway=opening_gateway
        self.freshness=FactFreshnessPolicy({FactType.PLACE_LOCATION:FreshnessRule(max_age_seconds=86400),
            FactType.WEATHER_FORECAST:FreshnessRule(max_age_seconds=FORECAST_TTL),FactType.OPENING_HOURS:FreshnessRule(max_age_seconds=30)})
        self.authority=FactAuthorityPolicy.existing_providers()
        self.authority.rules[FactType.PLACE_LOCATION,"open_meteo_geocoding","structured_api"]=AuthorityRule(level="specialist",rank=80)
        for provider in ("nanjing_museum","zhejiang_museum"):
            self.authority.rules[FactType.OPENING_HOURS,provider,"official_notice"]=AuthorityRule(level="authoritative",rank=100)
        self.repository=InMemoryFactRepository(max_subjects=128,history_per_subject=64)
        self.places=TravelFactService(self.repository,self.freshness,self.authority,
            [CityLocationAdapter(self.freshness,geocoder,clock)],clock=clock)

    async def plan_opening_hours(self,text,recent_turns):
        if re.search(r"现在|此刻|当前|实时",text):
            return ForecastPlan(message="我只能核实已发布的开放安排，不能确认场馆现在是否实际开着。")
        def entities(message):
            refs=[]
            if "南京博物院" in message: refs.append("amap:B001907TGR")
            if "浙江省博物馆" in message and "之江" in message: refs.append("amap:B0I15SU50Z")
            return refs
        refs=entities(text)
        if len(refs)>1: return ForecastPlan(message="你想核实哪一家场馆的开放安排？",clarification=True)
        if not refs and re.search(r"灵隐|飞来峰|孤山|西湖博物馆",text):
            return ForecastPlan(message="这个场馆暂时没有接入可核实的日期公告，我不能确认其开放时间。")
        if not refs and "浙江省博物馆" in text:
            return ForecastPlan(message="你问的是浙江省博物馆哪个馆区？目前可核实之江馆区的限定日期公告。",clarification=True)
        if not refs and "西湖" in text:
            return ForecastPlan(message="你指的是西湖的哪处具体设施或场馆？整个开放景观不能统一给一个关门时间。",clarification=True)
        if not refs:
            # Inherit only a referential/generic follow-up. An explicit unknown
            # venue mention must never acquire the prior venue's identity.
            def generic_followup(message):
                return not re.sub(r"今天|明天|后天|(?:\d{4}年)?\d{1,2}月\d{1,2}[日号]|周[一二三四五六日天]|开门|关门|开馆|闭馆|开放时间|营业时间|开放|营业|几点|什么时候|这个|这家|它|那里|博物馆|场馆|景点|还能进去|能进馆|吗|呢|呀|啊|那|[？?，,。！!\s]", "",message)
            if generic_followup(text):
                for turn in reversed(recent_turns):
                    mentions=entities(turn.get("user",""))
                    if len(mentions)==1: refs=mentions;break
                    # Opaque intervening turns end focus; do not infer whether an
                    # unsupported string is an entity using a model or POI guess.
                    if mentions or not generic_followup(turn.get("user","")): break
        if not refs: return ForecastPlan(message="你想问哪一家具体场馆？请给出场馆名称。",clarification=True)
        ref=refs[0]; name,city,_,_=VENUES[ref]
        local=self.clock().astimezone(ZoneInfo("Asia/Shanghai")); target=None
        relatives=re.findall(r"今天|明天|后天",text)
        dates=re.findall(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})[日号]",text)
        weekday=re.findall(r"周([一二三四五六日天])",text)
        if len(set(relatives))+len(dates)+len(set(weekday))>1:
            return ForecastPlan(message="请指定一个明确日期。",clarification=True)
        try:
            if dates:
                year,month,day=dates[0]; target=local.date().replace(year=int(year or local.year),month=int(month),day=int(day))
            elif relatives: target=local.date()+timedelta(days={"今天":0,"明天":1,"后天":2}[relatives[0]])
            elif weekday:
                day="一二三四五六日".index("日" if weekday[0]=="天" else weekday[0]);target=local.date()+timedelta(days=(day-local.weekday())%7)
            elif "国庆" in text and re.search(r"第二天|第2天",text):
                years=re.findall(r"(\d{4})年",text)
                target=local.date().replace(year=int(years[0]) if years else local.year,month=10,day=2)
        except ValueError: pass
        if target is None: return ForecastPlan(message="你想核实哪一天的开放安排？请给出日期。",clarification=True)
        start=datetime.combine(target,datetime.min.time(),tzinfo=ZoneInfo("Asia/Shanghai"))
        req=FactRequirement(fact_type=FactType.OPENING_HOURS,subject=PlaceSubject(ref=ref,name=name,destination=city),
            time_scope=TimeScope(start=start,end=start+timedelta(days=1)),minimum_authority="authoritative",allow_stale=False,
            required_freshness_seconds=30,reason="Companion official published date opening schedule")
        return ForecastPlan(requirements=[req],location_label=name,timezone="Asia/Shanghai")

    async def plan_forecast(self,text,destination,recent_turns):
        # Unsupported current/past/alert never consumes location/network tools.
        if re.search(r"现在|此刻|当前|实时|刚才|昨天|前天|预警|警报",text):
            return ForecastPlan(message="我目前只支持未来小时预报，不能核实当前实测天气、过去天气或气象预警。")
        named=forecast_location_mentions(text, statement=True)
        if len(named)>1: return ForecastPlan(message="你提到了多个地点，请指定要查询天气的一个城市。",clarification=True)
        if "西湖区" in text and named == ["西湖区"] and not destination:
            return ForecastPlan(message="你指的是哪个城市的西湖区？请先明确城市。",clarification=True)
        city=named[0] if named else destination
        if not city:
            # Recover explicit destination statements, not assistant proposals.
            for turn in reversed(recent_turns):
                matches=forecast_location_mentions(turn.get("user", ""), statement=True)
                if len(matches)==1: city=matches[0];break
        if "西湖" in text and "西湖区" not in text and (not city or city.startswith("西湖")): city="杭州"
        if not city: return ForecastPlan(message="你想看哪个城市的天气预报？",clarification=True)
        # Missing date is resolved before provider work; location timezone still owns relative date conversion.
        if not re.search(r"今天|明天|后天|\d{1,2}月\d{1,2}[日号]",text):
            return ForecastPlan(message="你想看哪一天的天气预报？",clarification=True)
        async def resolve_city(name):
            req=FactRequirement(fact_type=FactType.PLACE_LOCATION,subject=PlaceSubject(ref="city-search:"+name,name=name,destination=name),
                required_freshness_seconds=86400,minimum_authority="specialist",allow_stale=False,reason="forecast internal location prerequisite")
            return await self.places.resolve_fact(req)
        place=await resolve_city(city)
        if place.resolution_status == "no_evidence":
            # One bounded semantic extraction when lexical search has no exact
            # provider match. Never substitute old context after an explicit
            # new mention, or treat a model-proposed substring as a resolved city.
            try:
                candidates=await self.location_extractor(text)
            except Exception:
                candidates=[]
            if not isinstance(candidates,list):
                candidates=[]
            candidates=list(dict.fromkeys(c for c in candidates if isinstance(c,str)
                and 2<=len(c)<=24 and c in text and re.fullmatch(r"[\u4e00-\u9fff]+",c)
                and ("省" not in city or "省" in c)))[:2]
            if len(candidates)>1:
                return ForecastPlan(message="你提到了多个地点，请指定要查询天气的一个城市。",clarification=True)
            if candidates and candidates[0]!=city:
                city=candidates[0]
                place=await resolve_city(city)
        if place.resolution_status == "conflicting":
            options=list(dict.fromkeys(str(e.metadata.get("admin1", ""))+str(e.metadata.get("city_name", "")) for e in place.conflicting_evidence))
            return ForecastPlan(place_result=place,message=f"“{city}”对应多个城市（{'、'.join(options)}），请补充省份。",clarification=True)
        if not place.usable_as_current or not isinstance(place.value,LocationValue):
            if re.search(r"和|还是|或者|以及|与",city) and place.resolution_status == "no_evidence":
                return ForecastPlan(place_result=place,message="你可能提到了多个地点，请指定要查询天气的一个城市。",clarification=True)
            return ForecastPlan(place_result=place,message=f"已识别你提供的地点“{city}”，但我现在没有拿到可靠的地点坐标，无法核实天气预报。")
        meta=place.selected_evidence[0].metadata; timezone=str(meta["timezone"])
        window,message,clarify=time_window(text,timezone,self.clock())
        label=city+"（西湖附近的城市级预报）" if "西湖" in text and city=="杭州" else city+"（城市级预报）"
        if window is None: return ForecastPlan(place_result=place,location_label=label,timezone=timezone,message=message,clarification=clarify)
        subject=DestinationSubject(ref="geonames:"+str(meta["geonames_id"]),location=place.value.point)
        start,end=window; requirements=[]
        while start<end:
            requirements.append(FactRequirement(fact_type=FactType.WEATHER_FORECAST,subject=subject,time_scope=TimeScope(start=start,end=start+timedelta(hours=1)),
                required_freshness_seconds=FORECAST_TTL,minimum_authority="specialist",allow_stale=False,reason="Companion future hourly forecast"))
            start+=timedelta(hours=1)
        return ForecastPlan(requirements=requirements,place_result=place,location_label=label,timezone=timezone)

    async def resolve_facts(self,requirements):
        if any(r.fact_type not in {FactType.WEATHER_FORECAST,FactType.OPENING_HOURS} or r.allow_stale or r.time_scope is None for r in requirements):
            raise ValueError("Companion fact tool accepts only approved non-stale forecast or opening requirements")
        # One payload per location/UTC day per turn; failures shared, never retried 24 times.
        payloads={}
        async def gateway(subject,scope,now):
            key=(subject.ref,scope.start.astimezone(UTC).date())
            if key not in payloads:
                try: payloads[key]=await self.weather_gateway(subject,scope,now)
                except Exception as exc: payloads[key]=exc
            if isinstance(payloads[key],Exception): raise payloads[key]
            return payloads[key]
        weather=TravelFactService(self.repository,self.freshness,self.authority,[WeatherForecastAdapter(self.freshness,gateway=gateway)],clock=self.clock)
        # Hours cannot reuse cross-turn cache after a network failure.
        hours=TravelFactService(InMemoryFactRepository(),self.freshness,self.authority,
            [OfficialOpeningHoursAdapter(self.freshness,self.opening_gateway,self.clock)],clock=self.clock)
        return [await (hours if r.fact_type==FactType.OPENING_HOURS else weather).resolve_fact(r) for r in requirements]

def forecast_text(plan: ForecastPlan, results: Sequence[ResolvedFact], request: str = "") -> str:
    if plan.message: return plan.message
    good=[r for r in results if r.resolution_status=="resolved" and r.usable_as_current and r.freshness_status=="fresh" and
        r.selected_fact and r.selected_fact.nature=="provider_prediction" and r.value.kind=="weather"]
    if not good:
        return "当前天气预报数据存在冲突，无法给出可靠的单一预报。" if any(r.resolution_status=="conflicting" for r in results) else "我现在没有拿到可靠的天气预报数据，暂时无法确认这个时段。"
    good=sorted(good,key=lambda r:r.requirement.time_scope.start)
    zone=ZoneInfo(plan.timezone)
    retrieved=min(e.retrieved_at for r in good for e in r.selected_evidence).astimezone(zone)
    day=good[0].requirement.time_scope.start.astimezone(zone)
    partial=len(good)!=len(plan.requirements)
    if re.search(r"逐小时|每小时|按小时|小时明细|详细.*(?:天气|预报)|(?:天气|预报).*详细",request):
        rows=[]
        for r in good:
            start=r.requirement.time_scope.start.astimezone(zone);end=r.requirement.time_scope.end.astimezone(zone)
            rows.append(f"{start:%H:%M}–{end:%H:%M}：预计气温{r.value.temperature_celsius:g}°C，降水概率{r.value.precipitation_probability_percent:g}%")
        text=f"{plan.location_label}，{day:%Y年%m月%d日}的逐小时预报（当地时间）：\n"+"\n".join(rows)
    else:
        offset=(day.date()-retrieved.date()).days
        date_label={0:"今天",1:"明天",2:"后天"}.get(offset,f"{day.month}月{day.day}日")
        part=next((p for p in DAYPARTS if p in request),None)
        scope=date_label+(part if part else "接下来" if offset==0 else "")
        location=plan.location_label.split("（",1)[0]
        probabilities=[r.value.precipitation_probability_percent for r in good]
        peak=max(probabilities)
        # These are wording bands for individual hourly probabilities, never
        # a calculated probability for the entire day or a rainfall intensity.
        rain="下雨的可能性较大" if peak>=60 else "有可能下雨" if peak>=30 else "下雨的可能性较低"
        temperatures=[r.value.temperature_celsius for r in good]
        low,high=math.floor(min(temperatures)),math.ceil(max(temperatures))
        temperature=f"预计气温约{low}–{high}°C" if low!=high else f"预计气温约{low}°C"
        temp_only=bool(re.search(r"气温|温度|多少度",request) and not re.search(r"天气|下雨|降雨",request))
        if temp_only:
            text=f"{location}{scope}{temperature}。"
        else:
            advice="，出门建议带伞" if peak>=60 else "，出门可以备把伞" if peak>=30 else ""
            text=f"{location}{scope}{rain}{advice}。"
            # Only join adjacent verified hours, preserving gaps and multiple
            # rain windows rather than implying uninterrupted coverage.
            windows=[]
            for r in good:
                if r.value.precipitation_probability_percent<60:
                    continue
                start=r.requirement.time_scope.start.astimezone(zone)
                end=r.requirement.time_scope.end.astimezone(zone)
                if windows and windows[-1][1]==start:
                    windows[-1]=(windows[-1][0],end)
                else:
                    windows.append((start,end))
            focus=""
            if 0<len(windows)<=2:
                focus="其中"+"、".join(f"{start:%H:%M}–{end:%H:%M}" for start,end in windows)+"较容易下雨。"
            elif len(windows)>2:
                focus="有多个时段的降雨可能性较高。"
            probability=""
            if re.search(r"概率|几成|百分之",request):
                low_probability,high_probability=min(probabilities),max(probabilities)
                probability=(f"已查到的各小时降水概率为{low_probability:g}%–{high_probability:g}%。"
                    if low_probability!=high_probability else f"已查到的各小时降水概率均为{high_probability:g}%。")
            text+="\n\n"+focus+probability+temperature+"。"
    if partial:
        text="目前只查到了部分时段的预报。"+text+"缺失时段暂时无法判断。"
    return text

@lru_cache
def get_default_fact_tool(): return CompanionFactAdapter()
