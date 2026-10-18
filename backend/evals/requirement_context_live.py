"""Real-model B follow-up; stdin in isolated API18004 container only.

Creates a new labelled fixture, never edits an existing/production trip. No
credentials or private histories are emitted. Static schedules are test inputs,
not verified venue availability, bookings or proof of physical visits.
"""
import json
import os
import time
import urllib.request
from urllib.error import HTTPError
from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import uuid4
from zoneinfo import ZoneInfo

assert os.environ.get("ROAMSYNC_ISOLATED_INTEGRATION") == "1"
assert os.environ["DATABASE_URL"].endswith("/roamsync_v2_integration")
headers = {"X-RoamSync-Access": os.environ["ROAMSYNC_INTEGRATION_TOKEN"], "Content-Type": "application/json"}
out = {"scope": "new labelled isolated Trip, actual model/Graph/Validator/Accept; no real booking/visit", "checks": []}


def api(path, method="GET", body=None):
    out["last_request"] = {"method": method, "path": path}
    req = urllib.request.Request("http://127.0.0.1:8000/api/v1" + path,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        out["http_error"] = {"status": exc.code, "body": exc.read().decode("utf-8")[:2000]}
        raise


try:
    places = []
    for name in ["杭州博物馆", "河坊街", "中国丝绸博物馆"]:
        found = api("/places/search?" + urlencode({"city": "杭州", "query": name}))["items"]
        exact = [p for p in found if p["name"] == name]
        assert exact, name
        p = exact[0]
        assert p["identity_status"] == "provider_identity"
        places.append(p)
    day0 = datetime.now(ZoneInfo("Asia/Shanghai")).date() + timedelta(days=1)
    draft = api("/drafts", "POST", {"city": "杭州", "title": "B 多轮背景与保护验收 " + str(uuid4())[:8],
        "day_count": 3, "requirements": "步行上限30分钟，喜欢拍照，仅用于软件验收，此次验收未实际到访"})
    out["draft_id"] = draft["id"]
    path = "/drafts/" + draft["id"]
    assert not any("验收" in r["text"] or "到访" in r["text"] for r in draft["requirement_records"])
    walking = next(r for r in draft["requirement_records"] if r["key"] == "max_walking_minutes")
    draft = api(path + "/requirements/revoke", "POST", {"expected_version": draft["version"], "requirement_id": walking["id"], "day_index": 2})
    draft = api(path + "/edit", "POST", {"expected_version": draft["version"],
        "title": draft["title"], "requirements": draft["requirements"], "plan": {"days": [
        {"day_index": n + 1, "title": "软件验收", "items": [{"name": p["name"], "place_id": p["ref"]["place_id"],
         "note": "人工指定测试活动，不证明开放、预约或到访"}]} for n, p in enumerate(places)]}})
    draft = api(path + "/save", "POST", {"expected_version": draft["version"]})
    prepared = api(path + "/promotion-preview", "POST", {"expected_version": draft["version"], "start_date": str(day0),
        "duration_minutes": 60, "max_walking_minutes": 180, "daily_start_time": "15:00", "daily_end_time": "18:00"})
    assert not prepared["coverage"]["blockers"], prepared["coverage"]
    operation = api("/draft-promotions", "POST", {"request_id": str(uuid4()), "prepared_id": prepared["id"],
        "prepared_hash": prepared["prepared_hash"], "action": "create_and_adopt", "confirmation": "创建并采用当前方案"})
    operation = api("/draft-promotions/" + operation["id"] + "/resume", "POST", {})
    assert operation["status"] == "applied"
    trip_id = operation["target_trip_id"]
    out["trip_id"] = trip_id
    trip_path = "/trips/" + trip_id
    context = api(trip_path + "/planning-context")
    third = context["days"][2]["activities"][0]
    api("/activities/" + third["id"], "PUT", {"version": third["version"], "schedule_locked": True})
    # Explicit record endpoint emulates a historical contaminated record. Keep
    # its provenance in records while excluding it from effective projection.
    requirements = api(trip_path + "/requirements")
    requirements = api(trip_path + "/requirements", "POST", {"expected_version": requirements["version"], "text": "此次验收未实际到访"})
    legacy_id = requirements["records"][-1]["id"]
    assert all(legacy_id not in [r["id"] for r in rows] for rows in requirements["effective_by_date"].values())
    out["checks"].append("capture excludes provenance; historical raw record retained but excluded from effective per-day requirements")
    before = api(trip_path + "/planning-context")
    out["before_trip_version"] = before["trip"]["version"]
    target = before["days"][1]
    request = "只调整第2天河坊街的停留为45分钟，其他日期安排保持原样，第3天15点固定活动不要动，不要恢复第2天已撤销的步行不超过30分钟限制。先提出候选，等待我确认。"
    out["request"] = request
    resolution = api(trip_path + "/planning-intent/resolve", "POST", {"message": request,
        "selected_day_id": target["id"], "selected_activity_id": target["activities"][0]["id"]})
    out["resolution"] = resolution
    assert not resolution["requires_clarification"]
    run = api(trip_path + "/planning-runs", "POST", {"run_type": "replan", "user_request": request,
        "selected_day_id": target["id"], "selected_activity_id": target["activities"][0]["id"]})
    out["run_id"] = run["id"]
    for _ in range(100):
        run = api("/planning-runs/" + run["id"])
        if run["status"] in {"awaiting_confirmation", "awaiting_clarification", "failed", "completed"}:
            break
        time.sleep(3)
    out["run"] = run
    assert run["status"] == "awaiting_confirmation", run
    revision = api("/planning-runs/" + run["id"] + "/revision")
    out["revision"] = revision
    actual_effective = revision["before_snapshot"]["effective_requirements_by_date"]
    assert all(legacy_id not in [r["id"] for r in rows] for rows in actual_effective.values())
    assert all(r["key"] != "max_walking_minutes" for r in actual_effective[str(day0 + timedelta(days=1))])
    out["checks"].append("actual Graph Planner input excludes legacy provenance and revoked day2 walking limit")
    out["decision"] = api("/planning-runs/" + run["id"] + "/decision", "POST", {"decision": "accept"})
    after = api(trip_path + "/planning-context")
    out["before_days"] = before["days"]
    out["after_days"] = after["days"]
    out["after_trip_version"] = after["trip"]["version"]
    assert after["days"][1]["activities"][0]["duration_minutes"] == 45
    out["preserved_day_metadata_changes"] = {}
    for index in (0, 2):
        original = before["days"][index]["activities"][0]
        current = after["days"][index]["activities"][0]
        changed = {key: [original[key], value] for key, value in current.items() if original[key] != value}
        assert not (changed.keys() - {"version", "updated_at"}), changed
        out["preserved_day_metadata_changes"][str(index + 1)] = changed
    assert after["trip"]["version"] == before["trip"]["version"] + 1
    out["checks"].append("explicit Accept changes day2 duration once and preserves day1/day3 itinerary semantics including locked activity; version/timestamp changes recorded separately")
    # No implicit binding of cross-turn pronoun to arbitrary prior activity.
    ambiguous = api(trip_path + "/planning-intent/resolve", "POST", {"message": "把它改成45分钟，其他日期不要动"})
    out["unbound_pronoun_resolution"] = ambiguous
    assert ambiguous["requires_clarification"]
    out["checks"].append("unbound cross-turn pronoun asks clarification rather than silently selecting another activity")
    out["status"] = "passed"
except Exception as exc:
    out["status"] = "failed"
    out["failure_type"] = type(exc).__name__
    out["failure"] = str(exc)[:2000]
finally:
    print(json.dumps(out, ensure_ascii=False, indent=2))
