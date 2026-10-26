import asyncio
import json
import sys
import time
from typing import Any

from app.config import get_settings
from app.maps_service import MapProviderError, search_amap_cities, search_amap_location_pois
from app.openai_intent_parser import build_semantic_intent_provider
from app.planning_errors import PlannerProviderError


async def run() -> dict[str, Any]:
    settings = get_settings()
    report: dict[str, Any] = {
        "planner": {"configured": False, "ok": False},
        "amap": {"configured": bool(settings.amap_rest_key), "ok": False},
    }

    provider = build_semantic_intent_provider(settings)
    if provider is not None:
        report["planner"]["configured"] = True
        started = time.perf_counter()
        try:
            draft = await provider.extract(
                "陪我聊聊杭州",
                {"trip": {"destination": "杭州"}, "days": [], "activities": []},
            )
            report["planner"].update(
                {
                    "ok": True,
                    "parser": draft.parser,
                    "model": provider.model,
                    "total_tokens": provider.total_tokens,
                }
            )
        except PlannerProviderError as exc:
            report["planner"].update({"error_code": exc.code, "retryable": exc.retryable})
        report["planner"]["latency_ms"] = round(
            (time.perf_counter() - started) * 1000, 2
        )

    if settings.amap_rest_key:
        started = time.perf_counter()
        try:
            cities = await search_amap_cities("杭州")
            pois = await search_amap_location_pois("西湖", "杭州")
            report["amap"].update(
                {
                    "ok": bool(cities and pois),
                    "city_result_count": len(cities),
                    "poi_result_count": len(pois),
                    "first_result_has_provider_id": bool(pois and pois[0].poi_id),
                }
            )
            if not report["amap"]["ok"]:
                report["amap"]["error_code"] = "map_empty_success_response"
        except MapProviderError as exc:
            report["amap"].update(
                {"error_code": exc.code, "provider_code": exc.provider_code}
            )
        report["amap"]["latency_ms"] = round(
            (time.perf_counter() - started) * 1000, 2
        )
    return report


def main() -> None:
    if sys.platform == "win32":
        report = asyncio.run(run(), loop_factory=asyncio.SelectorEventLoop)
    else:
        report = asyncio.run(run())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["planner"]["ok"] or not report["amap"]["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
