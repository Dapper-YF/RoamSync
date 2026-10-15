"""Read-only source feasibility probe. Never emits credentials or request URLs with keys."""
import concurrent.futures
import hashlib
import json
import re
from datetime import UTC, datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import get_settings


def probe(job):
    label, url, mode = job
    result = {"source": label, "retrieved_at": datetime.now(UTC).isoformat()}
    if mode == "public":
        result["url"] = url
    try:
        with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as response:
            raw = response.read(3_000_000)
            result.update(http_status=response.status, content_type=response.headers.get("Content-Type"),
                          bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        if mode == "amap":
            payload = json.loads(raw)
            result.update(status=payload.get("status"), info=payload.get("info"), infocode=payload.get("infocode"))
            result["pois"] = [{k: p.get(k) for k in ("id", "name", "cityname", "adname", "address", "biz_ext", "business")}
                              for p in payload.get("pois", [])[:3]]
        else:
            html = raw.decode("utf-8", errors="replace")
            result["scripts"] = re.findall(r'<script[^>]+src=[\"\x27]?([^\"\x27\s>]+)', html)[:20]
            result["api_hints"] = re.findall(r'.{0,90}(?:baseURL|https?://[^\s\"\x27]+|newsDetails|article/detail|/api/|getNews|Opening|Hours).{0,90}', html)[:35]
            result["hours_tokens"] = re.findall(r'.{0,60}(?:开放时间|开馆|闭馆|停止入场|停止检票|国庆|中秋|09:00|17:00).{0,100}', html)[:20]
            result["prefix"] = re.sub(r'\s+', ' ', html[:300])
            result["notice_links"] = re.findall(r'<a[^>]+href=[\"\x27]([^\"\x27]+)[\"\x27][^>]*>[^<]*(?:国庆|开放)', html)[:10]
    except Exception as exc:
        result["error_type"] = type(exc).__name__  # Exception text may contain key-bearing URL.
        result["http_error_status"] = getattr(exc, "code", None)
    return result


settings = get_settings()
jobs = [("Nanjing official", "https://www.njmuseum.com/zh", "public"),
        ("Nanjing official alternate", "https://www.njmuseum.org.cn/zh/visitIndex", "public"),
        ("Zhejiang official", "https://www.zjmuseum.com.cn/cn/", "public"),
        ("Lingyin official English", "https://en.lingyinsi.org/maps/", "public"),
        ("Zhejiang official application", "https://www.zjmuseum.com.cn/cn/static/js/app.3c0c0d72.js", "public")]
if settings.amap_rest_key:
    for version in (3, 5):
        for name, city in (("南京博物院", "南京"), ("浙江省博物馆", "杭州")):
            params = {"key": settings.amap_rest_key, "keywords": name}
            params.update({"city": city, "citylimit": "true", "extensions": "all", "offset": 3} if version == 3
                          else {"region": city, "city_limit": "true", "show_fields": "business", "page_size": 3})
            jobs.append((f"AMap v{version} {name}", f"https://restapi.amap.com/v{version}/place/text?" + urlencode(params), "amap"))
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    results = list(executor.map(probe, jobs))
print(json.dumps({"amap_configured": bool(settings.amap_rest_key), "results": results}, ensure_ascii=False, indent=2))
