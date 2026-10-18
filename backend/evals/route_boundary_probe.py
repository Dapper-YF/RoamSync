"""Public landmark controls; never reads a device location, Trip or database.

Overseas values are deliberate unsupported-area inputs, not converted GPS fixes.
"""
import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys

from app.config import get_settings
from app.map_transport import MapProviderError
from app.place_content.contracts import GeoPoint, RouteQuery
from app.place_content.provider import AMapContentProvider


async def run(output: Path):
    assert os.environ.get("ROAMSYNC_ISOLATED_INTEGRATION") == "1"
    assert os.environ.get("DATABASE_URL", "").endswith("/roamsync_v2_integration")
    if output.exists():
        raise FileExistsError("Preserve existing evidence")
    provider = AMapContentProvider(get_settings().amap_rest_key)
    report = {"created_at": datetime.now(UTC).isoformat(), "device_location_used": False,
              "database_writes": 0, "cases": [],
              "limits": "Public landmark controls do not establish the cause of the previous phone failure"}
    for label, origin, destination in [
        ("hangzhou_public_nearby_walk", (120.166525, 30.239091), (120.16863, 30.2401)),
        ("beijing_chengdu_long_distance_walk", (116.40324, 39.9094), (104.057641, 30.65699)),
        ("singapore_unsupported_landmark_control", (103.8545, 1.2868), (103.8636, 1.2894)),
    ]:
        try:
            result = await provider.route(RouteQuery(origin=GeoPoint(longitude=origin[0], latitude=origin[1]),
                destination=GeoPoint(longitude=destination[0], latitude=destination[1]), mode="walk"))
            row = {"case": label, "status": "available", "distance_meters": result.distance_meters,
                   "duration_seconds": result.duration_seconds, "estimated_fallback": result.is_estimated_fallback}
        except MapProviderError as exc:
            row = {"case": label, "status": "unavailable", "code": exc.code,
                   "provider_code": exc.provider_code, "http_status": exc.status_code}
        report["cases"].append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(run(Path(sys.argv[1])))
