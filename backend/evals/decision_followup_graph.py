"""New isolated Trip: actual model/Graph/Validator/explicit Accept.

Run inside API18004 only after root synchronizes API and Worker. Preparation is
through real product draft/adoption APIs and exact provider snapshots. No
existing trip is edited, no fixture expense or venue operating fact is invented.
"""
import asyncio
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

assert os.environ.get("ROAMSYNC_ISOLATED_INTEGRATION") == "1"
assert os.environ["DATABASE_URL"].endswith("/roamsync_v2_integration")
parser = argparse.ArgumentParser()
parser.add_argument("--case", choices=["walking_only", "landscape_priority"], default="walking_only")
case = parser.parse_args().case
headers = {"X-RoamSync-Access": os.environ["ROAMSYNC_INTEGRATION_TOKEN"], "Content-Type": "application/json"}
out = {"scope": "new labelled isolated Trip; actual Provider/model/Graph/Validator/Accept",
       "case": case,
       "user_priority": "landscape_photography_over_walking_saving_if_supported" if case == "landscape_priority" else "walking_saving_without_category_preference",
       "runtime_api_source_hashes": {name: hashlib.sha256(Path("/app/app", name).read_bytes()).hexdigest()
            for name in ["candidate_decisions.py", "openai_planner.py", "planning_graph.py", "planning_explanation.py", "planning_intent_service.py"]},
       "limits": ["preparation_not_Web_UI", "no_verified_booking_or_visit", "taxonomy_cost_estimates_not_provider_prices",
                  "one_directed_anchor_leg_not_whole_day"], "checks": []}


def api(path, method="GET", body=None):
    out["last_step"] = {"path": path, "method": method}
    request = urllib.request.Request("http://127.0.0.1:8000/api/v1" + path,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = json.loads(exc.read()).get("detail")
        out["http_error"] = {"status": exc.code, "detail": detail}
        raise


async def persist_candidates(trip_id):
    from app.database import session_factory
    from app.maps_service import search_amap_places
    from app.planner_repository import save_candidate_snapshot
    found = []
    async with session_factory() as session:
        for name in ("西湖风景名胜区", "中国丝绸博物馆"):
            matches = [p for p in await search_amap_places(name, "杭州")
                if p.name.removeprefix("杭州市").removeprefix("杭州") == name]
            assert len(matches) == 1, "exact provider identity required"
            p = await save_candidate_snapshot(session, UUID(trip_id), matches[0])
            found.append({"id": str(p.id), "name": p.name, "category": p.category,
                          "source": matches[0].source_url, "estimated_cost_fen": p.estimated_cost_fen})
        await session.commit()
    return found


try:
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)
    anchor = api("/places/search?" + urlencode({"city": "杭州", "query": "雷峰塔景区"}))["items"]
    anchor = next(p for p in anchor if p["name"].removeprefix("杭州") == "雷峰塔景区")
    assert anchor["identity_status"] == "provider_identity"
    draft = api("/drafts", "POST", {"city": "杭州", "title": "C 决策完整链验收 " + case + " " + str(uuid4())[:8],
        "day_count": 1, "requirements": ""})
    out["draft_id"] = draft["id"]
    path = "/drafts/" + draft["id"]
    draft = api(path + "/edit", "POST", {"expected_version": draft["version"], "title": draft["title"], "requirements": "", "plan": {"days": [
        {"day_index": 1, "title": "测试固定活动", "items": [{"name": anchor["name"], "place_id": anchor["ref"]["place_id"],
            "note": "软件验收指定活动，非预约或实际到访证明"}]}]}})
    draft = api(path + "/save", "POST", {"expected_version": draft["version"]})
    prepared = api(path + "/promotion-preview", "POST", {"expected_version": draft["version"], "start_date": str(day),
        "duration_minutes": 60, "max_walking_minutes": 180, "daily_start_time": "14:00", "daily_end_time": "18:00"})
    assert not prepared["coverage"]["blockers"]
    operation = api("/draft-promotions", "POST", {"request_id": str(uuid4()), "prepared_id": prepared["id"],
        "prepared_hash": prepared["prepared_hash"], "action": "create_and_adopt", "confirmation": "创建并采用当前方案"})
    operation = api("/draft-promotions/" + operation["id"] + "/resume", "POST", {})
    assert operation["status"] == "applied"
    trip_id = operation["target_trip_id"]
    out["trip_id"] = trip_id
    trip_path = "/trips/" + trip_id
    context = api(trip_path + "/planning-context")
    fixed = context["days"][0]["activities"][0]
    api("/activities/" + fixed["id"], "PUT", {"version": fixed["version"], "schedule_locked": True})
    prefs = api(trip_path + "/preferences")
    fields = ("version", "pace", "interest_categories", "transport_modes", "daily_start_time", "daily_end_time",
              "meal_preferences", "avoid_categories", "max_walking_minutes", "free_text_requirements")
    change = {k: prefs[k] for k in fields}
    change.update(daily_start_time="09:00", interest_categories=["nature", "photography"] if case == "landscape_priority" else [], transport_modes=["walk"])
    api(trip_path + "/preferences", "PUT", change)
    requirements = api(trip_path + "/requirements")
    api(trip_path + "/requirements", "POST", {"expected_version": requirements["version"],
        "text": "当天预算不超过500元", "key": "daily_budget_fen", "value": 50000, "strength": "hard",
        "day_date": str(day)})
    out["prepared_candidates"] = asyncio.run(persist_candidates(trip_id))
    before = api(trip_path + "/planning-context")
    out["before"] = before
    priority = ("仍希望尽量少走路，但喜欢自然景观摄影，景观体验比节省步行更重要，可以为有依据的景观体验接受额外步行；仍请避免无收益的绕路，说明实际步行代价与得到的体验，不要只按类别或评级选点。"
                if case == "landscape_priority" else "尽量少走路；")
    request = "重新规划第1天，只选一个现有候选地点作为上午游览，" + priority + "14点锁定活动保持原样。预算按有效要求，实际消费未知时不要宣称预算合规。"
    out["request"] = request
    run = api(trip_path + "/planning-runs", "POST", {"run_type": "replan", "user_request": request,
        "selected_day_id": before["days"][0]["id"]})
    out["run_id"] = run["id"]
    for _ in range(120):
        run = api("/planning-runs/" + run["id"])
        if run["status"] in {"awaiting_confirmation", "awaiting_clarification", "failed", "completed"}:
            break
        time.sleep(2)
    out["run"] = run
    assert run["status"] == "awaiting_confirmation", run
    revision = api("/planning-runs/" + run["id"] + "/revision")
    out["revision"] = revision
    assert revision["validation_result"]["valid"]
    review = revision["difference_summary"]["decision_review"]
    assert review["explanation_errors"] == []
    assert review["selection_tradeoffs"], "same-anchor comparison must actually reach Planner and final review"
    assert any(r["status"] == "not_evaluable" and r["evidence"].get("limit_fen") for r in review["effective_requirement_results"])
    out["checks"].append("real model produced candidate; Graph/Validator pass with budget unknown and persisted walking tradeoff")
    out["decision"] = api("/planning-runs/" + run["id"] + "/decision", "POST", {"decision": "accept"})
    after = api(trip_path + "/planning-context")
    out["after"] = after
    fixed_after = next(a for a in after["days"][0]["activities"] if a["id"] == fixed["id"])
    assert fixed_after["scheduled_time"] == "14:00:00" or fixed_after["scheduled_time"] == "14:00"
    assert fixed_after["duration_minutes"] == 60
    assert after["trip"]["version"] == before["trip"]["version"] + 1
    assert len(after["days"][0]["activities"]) == 2
    out["checks"].append("explicit Accept increments itinerary once; preserves fixed activity; formal reread contains chosen place and real route")
    out["status"] = "passed"
except Exception as exc:
    out.update(status="failed", failure_type=type(exc).__name__, failure=str(exc)[:2000])
finally:
    print(json.dumps(out, ensure_ascii=False, indent=2))
