"""Reviewed official CMS collectors. Published schedules do not assert live operation."""
import asyncio
import html
import json
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .models import FactBundle, FactType, OpeningHoursValue, TimeScope
from .normalization import evidence_record, fact_record

ZONE = ZoneInfo("Asia/Shanghai")
VENUES = {
    "amap:B001907TGR": ("南京博物院", "南京", "nanjing_museum", 381205),
    "amap:B0I15SU50Z": ("浙江省博物馆之江馆区", "杭州", "zhejiang_museum", 46554),
}
SOURCES = {
    "nanjing_museum": ("https://www.njmuseum.com/api/news/freshNotice", {"language": "zh"}, True),
    "zhejiang_museum": ("https://www.zjmuseum.com.cn/api/content/page", {"siteId": 22, "categoryCode": "Notice", "pageNum": 1, "pageSize": 10}, False),
}

async def official_gateway(provider):
    url, data, form = SOURCES[provider]
    def fetch():
        body = (urlencode(data) if form else json.dumps(data)).encode()
        request = Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"})
        with urlopen(request, timeout=12) as response:
            raw = response.read(1_048_577)
        if len(raw)>1_048_576: raise ValueError("official response too large")
        return json.loads(raw)
    payload = await asyncio.to_thread(fetch)
    return payload

def plain(body):
    return html.unescape(re.sub(r"<[^>]+>", "", body))

def reviewed_schedule(provider, payload, target):
    """Only reviewed 2026 notice grammar; changes fail closed, never model extraction."""
    if provider == "nanjing_museum":
        if payload.get("code") != 0: raise ValueError("official CMS status")
        notices=payload["data"]["list"]
        selected=[n for n in notices if n.get("id")==381205 and n.get("time")=="2026-09-17"]
        if len(selected)!=1: return None
        notice=selected[0]; body=plain(notice["introduction"])
        # A newer opening/closure notice cannot be silently ignored. Gallery
        # announcements do not become whole-museum closure records.
        if any(n.get("time", "")>notice["time"] and re.search(r"开放|闭馆|闭院|暂停",n.get("title","")) for n in notices):
            return None
        if "2026年中秋、国庆" not in body: return None
        if re.search(r"暂停|临时闭馆|维修|停止开放",body): return None
        if "闭馆" in body.replace("10月5日（周一）不闭馆", ""): return None
        grammar=r"(\d+)月(\d+)日(?:-(\d+)月(\d+)日)?开放时间(?:为|恢复为)(\d+):(\d+)—(\d+):(\d+)（(\d+):(\d+)停止入馆）"
        rows=re.findall(grammar,body)
        if len(rows)!=4: return None
        publication=notice["time"]
        updated="unknown"
        url="https://www.njmuseum.com/zh/newsDetails?id=381205"
    else:
        if payload.get("success") is not True: raise ValueError("official CMS status")
        notices=payload["data"][2]
        selected=[n for n in notices if n.get("content_id")==46554 and n.get("create_time","").startswith("2026-09-")]
        if len(selected)!=1: return None
        notice=selected[0]
        if any(n.get("create_time", "")>notice["create_time"] and re.search(r"开放|开馆|闭馆|暂停",n.get("title","")) for n in notices): return None
        body=plain(notice["content"])
        if "之江馆区" not in body or "孤山馆区" not in body: return None
        body=body.split("之江馆区",1)[1].split("孤山馆区",1)[0]
        # Year is established by the dated official publication plus reviewed
        # 2026 weekday consistency, not current year or a model guess.
        grammar=r"(\d+)月(\d+)日（周[一二三四五六日]）(?:至(\d+)月(\d+)日（周[一二三四五六日]）)?场馆开放时间为(\d+):(\d+)-(\d+):(\d+)，(\d+):(\d+)停止入馆"
        rows=re.findall(grammar,body)
        if len(rows)!=3: return None
        for month,day,weekday in re.findall(r"(\d+)月(\d+)日（周([一二三四五六日])）",body):
            if datetime(2026,int(month),int(day)).weekday()!="一二三四五六日".index(weekday): return None
        publication=notice.get("publish_date") or "unknown"
        updated=notice.get("update_time") or "unknown"
        url="https://www.zjmuseum.com.cn/cn/#/Notice"
        if re.search(r"暂停|临时闭馆|维修|停止开放",body) or body.count("闭馆")!=2: return None
        for month,day in re.findall(r"(\d+)月(\d+)日（周[一二三四五六日]）闭馆",body):
            if target==datetime(2026,int(month),int(day)).date():
                return dict(closed=True,publication=publication,updated=updated,url=url,notice_id=46554,body=body,semantics="special_exception")
    for m,d,em,ed,oh,om,ch,cm,ah,am in rows:
        first=datetime(2026,int(m),int(d)).date()
        last=datetime(2026,int(em or m),int(ed or d)).date()
        if first<=target<=last:
            return dict(closed=False,open=f"{int(oh):02}:{int(om):02}",close=f"{int(ch):02}:{int(cm):02}",
                admission=f"{int(ah):02}:{int(am):02}",publication=publication,updated=updated,url=url,notice_id=notice.get("id",notice.get("content_id")),
                body=body,semantics="date_specific_schedule")
    return None

class OfficialOpeningHoursAdapter:
    name, read_through = "official_opening_hours", True
    def __init__(self, freshness, gateway=official_gateway, clock=lambda:datetime.now(UTC)):
        self.freshness,self.gateway,self.clock=freshness,gateway,clock
    def supports(self, req): return req.fact_type==FactType.OPENING_HOURS and req.subject.ref in VENUES
    async def fetch(self, req, *, now):
        venue=VENUES[req.subject.ref]
        if req.subject.name!=venue[0] or req.subject.destination!=venue[1] or req.time_scope is None: return FactBundle()
        start=req.time_scope.start.astimezone(ZONE)
        if start.time()!=datetime.min.time() or req.time_scope.end!=start+timedelta(days=1): return FactBundle()
        payload=await self.gateway(venue[2]); retrieved=self.clock()
        schedule=reviewed_schedule(venue[2],payload,start.date())
        if schedule is None: return FactBundle()
        def local(time): return datetime.fromisoformat(f"{start.date()}T{time}:00").replace(tzinfo=ZONE)
        intervals=() if schedule["closed"] else (TimeScope(start=local(schedule["open"]),end=local(schedule["close"])),)
        value=OpeningHoursValue(intervals=intervals,closed_all_day=schedule["closed"],local_date=str(start.date()),timezone=ZONE.key,
            schedule_semantics=schedule["semantics"],last_admission=None if schedule["closed"] else local(schedule["admission"]))
        evidence=evidence_record(provider=venue[2],source_type="official_notice",source_reference=schedule["url"],retrieved_at=retrieved,
            authority_level="authoritative",normalized_snapshot={"notice_id":schedule["notice_id"],"value":value.model_dump(mode="json")},
            raw_payload=payload,metadata={"publication_time":schedule["publication"],"last_updated":schedule["updated"],"source_timezone":"not_supplied","exception_coverage":"published_notice_only",
                "closure_absence_verified":False,"identity_ref":req.subject.ref,"source_api":SOURCES[venue[2]][0]})
        fact=fact_record(fact_type=req.fact_type,subject=req.subject,value=value,evidence=evidence,freshness=self.freshness,
            nature="provider_assertion",effective_from=start,effective_until=start+timedelta(days=1),specificity="time_specific")
        return FactBundle(facts=(fact,),evidence=(evidence,))
