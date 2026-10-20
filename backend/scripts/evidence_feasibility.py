"""Bounded read-only provider probe. No database, private prompts or credentials emitted."""
import asyncio
import json
import sys
from pathlib import Path
from datetime import UTC, datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import Settings
from app.external_facts import search_tavily, extract_tavily
from app.place_content.provider import AMapContentProvider

async def main():
    settings = Settings(_env_file="E:/Study/RoamSync/.env")
    settings.tavily_proxy_url = settings.tavily_proxy_url.replace("host.docker.internal", "127.0.0.1")
    amap = AMapContentProvider(settings.amap_rest_key)
    report = {"at": datetime.now(UTC).isoformat(), "scenarios": []}
    for city, query in [("成都", "火锅"), ("成都", "六公里老火锅 玉林店"), ("南京", "南京博物院")]:
        row = {"city": city, "query": query}
        try:
            raw = await amap._request("v5/place/text", {"keywords": query, "region": city, "city_limit": "true", "page_size": 3, "show_fields": "business,photos"})
            row["amap"] = [{"name": p.get("name"), "id": p.get("id"), "address": p.get("address"), "business": p.get("business"), "photo_count": len(p.get("photos", []))} for p in raw.get("pois", [])[:3]]
        except Exception as exc:
            row["amap_error"] = type(exc).__name__
        try:
            fact = await search_tavily(settings, query=f"{city} {query} 特色 评价", max_results=3, include_images=True)
            results = fact.payload.get("results", [])
            urls = [p["url"] for p in results[:2]]
            extracted = await extract_tavily(settings, urls=urls) if urls else {}
            row["search"] = [{"url": p.get("url"), "title": p.get("title")} for p in results]
            row["extract"] = [{"url": p.get("url"), "characters": len(p.get("raw_content") or "")} for p in extracted.get("results", [])]
            row["failed_extract"] = [{"url": p.get("url")} for p in extracted.get("failed_results", [])]
            row["image_count"] = len(fact.payload.get("images", []))
        except Exception as exc:
            row["search_error"] = type(exc).__name__
        report["scenarios"].append(row)
    # Check the two restricted platforms directly through the same reader.
    try:
        extracted = await extract_tavily(settings, urls=["https://www.dianping.com/chengdu/ch10/g110", "https://cd.meituan.com/meishi/"])
        report["platform_pages"] = [{"url": p.get("url"), "characters": len(p.get("raw_content") or ""), "blocked_or_login": any(w in (p.get("raw_content") or "") for w in ["访问验证", "安全验证", "登录后", "验证码"])} for p in extracted.get("results", [])]
        report["platform_failed"] = [{"url": p.get("url")} for p in extracted.get("failed_results", [])]
    except Exception as exc:
        report["platform_error"] = type(exc).__name__
    out = ROOT.parent / "docs/evidence/evidence-assistant-20261020/provider-probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
