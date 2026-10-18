"""Opt-in, read-only AMap smoke through the content API; isolated in-memory DB.

Run: python -m evals.place_content_smoke --env-file E:/Study/RoamSync/.env
Reports only public POI projections/error codes. Never logs credentials or URLs
containing keys. Favorites are synthetic and exist only in the memory database.
"""
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.place_content.provider import AMapContentProvider
from app.place_content.repository import ContentRepository, metadata
from app.place_content.routes import create_router
from app.place_content.service import PlaceContentService


def smoke(key: str) -> dict:
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    metadata.create_all(engine)
    app = FastAPI()
    app.include_router(create_router(PlaceContentService(AMapContentProvider(key), ContentRepository(engine)), lambda: "synthetic-smoke-owner"))
    report = {"started_at": datetime.now(UTC).isoformat(), "provider": "amap", "mock": False, "production_database_accessed": False, "checks": []}

    def record(label, response):
        data = response.json() if response.content else None
        entry = {"check": label, "status_code": response.status_code}
        if response.status_code >= 400:
            entry["error"] = data.get("detail") if isinstance(data, dict) else "invalid_response"
        report["checks"].append(entry)
        return data, entry

    with TestClient(app) as client:
        selected = []
        for category, keyword in [("food", "杭帮菜"), ("attraction", "西湖")]:
            data, entry = record(f"search_{category}", client.get("/api/v1/places/search", params={"city": "杭州", "query": keyword, "category": category, "page_size": 3}))
            if entry["status_code"] != 200:
                continue
            entry["result_count"] = len(data["items"])
            if not data["items"]:
                continue
            place = data["items"][0]
            selected.append(place)
            entry["sample"] = {k: place[k] for k in ["ref", "name", "category", "location", "rating", "price", "image_status", "source"]}
            pid = place["ref"]["place_id"]
            detail, detail_entry = record(f"detail_{category}", client.get(f"/api/v1/places/{pid}"))
            if detail_entry["status_code"] == 200:
                detail_entry["identity_status"] = detail["identity_status"]
                detail_entry["same_id"] = detail["ref"]["place_id"] == pid
                detail_entry["freshness"] = detail["source"]["freshness"]
            record(f"favorite_{category}", client.put(f"/api/v1/me/favorites/{pid}"))
            record(f"favorite_repeat_{category}", client.put(f"/api/v1/me/favorites/{pid}"))
        saved, entry = record("favorites", client.get("/api/v1/me/favorites"))
        if entry["status_code"] == 200:
            entry["count"] = len(saved)
            entry["no_duplicates"] = len({i["place"]["ref"]["place_id"] for i in saved}) == len(saved)
        if selected:
            point = selected[0]["location"]
            data, entry = record("nearby", client.get("/api/v1/places/search", params={"longitude": point["longitude"], "latitude": point["latitude"], "category": "food", "page_size": 3}))
            if entry["status_code"] == 200:
                entry["result_count"] = len(data["items"])
        if len(selected) >= 2:
            for mode in ["walk", "driving"]:
                data, entry = record(f"route_{mode}", client.post("/api/v1/routes/query", json={"origin": selected[0]["location"], "destination": selected[1]["location"], "mode": mode}))
                if entry["status_code"] == 200:
                    entry.update(distance_meters=data["distance_meters"], duration_seconds=data["duration_seconds"], path_points=len(data["path"]), freshness=data["source"]["freshness"])
    report["tables"] = inspect(engine).get_table_names()
    report["model_client_imported"] = "app.model_client" in sys.modules
    report["formal_database_imported"] = "app.database" in sys.modules
    report["finished_at"] = datetime.now(UTC).isoformat()
    engine.dispose()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    values = dotenv_values(args.env_file)
    key = values.get("AMAP_REST_KEY") or values.get("amap_rest_key") or ""
    result = smoke(key)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
