"""Bounded real Graph/AMap/Accept probe using a previously adopted synthetic Trip."""
import asyncio
import json
from pathlib import Path
import sys
import time
from uuid import UUID, uuid4

import natural_assistant_runtime  # Explicitly isolated configuration before app imports.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import httpx
from app.database import session_factory
from app.planner_repository import save_candidate_snapshot
from app.schemas import PlaceSearchResultResponse

OUT = Path(__file__).resolve().parents[2] / "docs/evidence/natural-assistant"
source = Path(sys.argv[1])
previous = json.loads(source.read_text(encoding="utf-8"))
assert previous["result"].startswith("PASS")
tid = next(s["body"]["trip_id"] for s in previous["steps"] if s["step"] == "adopt")
report = {"kind": "real model Graph/AMap/Validator/Accept; synthetic user booking", "trip_id": tid, "source": source.name, "steps": []}
path = OUT / f"live-graph-{tid}-{uuid4()}.json"


def record(step, **data):
    report["steps"].append({"step": step, **data})
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(step, data.get("status", "recorded"), flush=True)


try:
    with httpx.Client(base_url="http://127.0.0.1:18019", timeout=140, trust_env=False) as c:
        before = c.get(f"/api/v1/trips/{tid}/arrangement-items").json()
        results = c.get(f"/api/v1/trips/{tid}/places/search", params={"q": "南京博物院"})
        results.raise_for_status()
        values = results.json()
        exact = [v for v in values if v["name"] == "南京博物院"]
        assert len(exact) == 1, "POI must be unambiguous"
        async def persist_fact():
            async with session_factory() as s, s.begin():
                place = await save_candidate_snapshot(s, UUID(tid), PlaceSearchResultResponse.model_validate(exact[0]))
                return str(place.id)
        place_id = asyncio.run(persist_fact())
        record("verified-poi", status=200, place_id=place_id, provider=exact[0]["provider"])
        day = next(d for d in before["days"] if d["date"] == "2026-11-08")
        item = next(i for i in before["items"] if "博物院" in i["label"])
        if not item["activity_id"]:
            scheduled = c.post(f"/api/v1/trips/{tid}/arrangement-items/{item['id']}/schedule", json={"expected_version": before["version"],
                "day_plan_id": day["id"], "place_id": place_id, "scheduled_time": "10:00", "duration_minutes": 60})
            record("explicit-synthetic-time-choice", status=scheduled.status_code, body=scheduled.json())
            scheduled.raise_for_status()
        before = c.get(f"/api/v1/trips/{tid}/arrangement-items").json()
        route = c.post(f"/api/v1/day-plans/{day['id']}/route", json={"mode": "walk"}, headers={"X-Trip-Version": str(before['version'])})
        record("real-route-refresh", status=route.status_code, body=route.json())
        route.raise_for_status()
        before = c.get(f"/api/v1/trips/{tid}/arrangement-items").json()
        request = "请把第二天南京博物院的停留时长改为90分钟，总统府不要动。玄武湖仍为备选，不安排。其他日期和留白保持不变。"
        response = c.post(f"/api/v1/trips/{tid}/planning-runs", json={"run_type": "replan", "selected_day_id": day["id"], "user_request": request})
        record("create-run", status=response.status_code, body=response.json())
        response.raise_for_status()
        run_id = response.json()["id"]
        for _ in range(95):
            run = c.get(f"/api/v1/planning-runs/{run_id}").json()
            if run["status"] in {"awaiting_confirmation", "awaiting_clarification", "failed", "cancelled", "accepted", "answered"}:
                break
            time.sleep(2)
        record("graph-result", status=200, body=run)
        assert run["status"] == "awaiting_confirmation", "Graph did not produce an adoptable candidate"
        rid = (run.get("pending_interrupt") or {}).get("revision_id")
        if not rid:
            revision = c.get(f"/api/v1/planning-runs/{run_id}/revision")
            revision.raise_for_status()
            rid = revision.json()["id"]
        response = c.post(f"/api/v1/plan-revisions/{rid}/accept")
        record("accept", status=response.status_code, body=response.json())
        response.raise_for_status()
        after = c.get(f"/api/v1/trips/{tid}/arrangement-items").json()
        record("readback", status=200, body=after)
        assert next(i for i in after["items"] if "博物院" in i["label"])["activity_id"]
        assert next(i for i in after["items"] if "玄武湖" in i["label"])["kind"] == "optional"
        assert any(a["schedule_locked"] and a["scheduled_time"] == "14:00:00" for d in after["days"] for a in d["activities"])
        assert before["days"][0] == after["days"][0]
        assert any(not leg["is_estimated"] for d in after["days"] for leg in d["route_legs"])
        report["result"] = "PASS real Graph, route facts, Validator, Accept and readback"
except Exception as exc:
    report["result"] = "FAIL"
    report["failure"] = {"type": type(exc).__name__, "message": str(exc)[:1000]}
finally:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report["result"], path, flush=True)
if report["result"] == "FAIL":
    raise SystemExit(1)
