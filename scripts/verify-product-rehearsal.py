"""Real provider/API write smoke, explicitly refused outside the rehearsal DB."""
import json
import os
import urllib.request
import urllib.error
from datetime import date, timedelta
from uuid import uuid4

assert os.environ.get("APP_ENV") == "test"
assert os.environ["DATABASE_URL"].endswith("/migration_rehearsal")
headers = {"X-RoamSync-Access": os.environ["ROAMSYNC_INTEGRATION_TOKEN"], "Content-Type": "application/json"}


def api(path, method="GET", body=None):
    req = urllib.request.Request("http://127.0.0.1:8000/api/v1" + path,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=150) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"API {method} {path.split('?')[0]} {error.code}: {error.read().decode()}") from None


checks = []
places = []
from urllib.parse import urlencode
for name in ["成都人民公园", "成都宽窄巷子景区"]:
    result = api("/places/search?" + urlencode({"city": "成都", "query": name}))
    assert result["items"], "real provider search empty"
    places.append(result["items"][0])
checks.append("real provider search and exact place detail")
pid = places[0]["ref"]["place_id"]
assert api("/places/" + pid)["ref"]["place_id"] == pid
api("/me/favorites/" + pid, "PUT")
assert api("/me/favorites/" + pid)["is_favorite"]
api("/me/travel-preferences", "PUT", {"interests": ["慢游"], "preferred_categories": ["attraction"]})
assert "慢游" in api("/me/travel-preferences")["interests"]
checks.append("persisted favorite and explicit preference")
route = api("/routes/query", "POST", {"origin": places[0]["location"], "destination": places[1]["location"], "mode": "walk"})
assert route["duration_seconds"] > 0 and route["distance_meters"] > 0
checks.append("real provider walking route")
draft = api("/drafts", "POST", {"city": "成都", "title": "仅迁移副本的发布验收", "day_count": 1, "requirements": "轻松游玩"})
path = "/drafts/" + draft["id"]
draft = api(path + "/edit", "POST", {"expected_version": draft["version"], "title": draft["title"], "requirements": draft["requirements"], "plan": {"days": [{"day_index": 1, "title": "成都慢游", "items": [{"name": p["name"], "place_id": p["ref"]["place_id"], "note": "真实地点"} for p in places]}]}})
draft = api(path + "/save", "POST", {"expected_version": draft["version"]})
assert api(path)["saved"]
checks.append("undated draft edit save and restore with provider identities")
preview = api(path + "/promotion-preview", "POST", {"expected_version": draft["version"], "start_date": str(date.today() + timedelta(days=20)), "duration_minutes": 60, "max_walking_minutes": 180})
assert not preview["coverage"]["blockers"], preview["coverage"]["blockers"]
before = len(api("/trips"))
body = {"request_id": str(uuid4()), "prepared_id": preview["id"], "prepared_hash": preview["prepared_hash"], "action": "create_and_adopt", "confirmation": "创建并采用当前方案"}
operation = api("/draft-promotions", "POST", body)
operation = api("/draft-promotions/" + operation["id"] + "/resume", "POST", {})
assert operation["status"] == "applied", operation["status"]
again = api("/draft-promotions", "POST", body)
assert again["id"] == operation["id"] and len(api("/trips")) == before + 1
assert api("/draft-promotions/" + operation["id"])["status"] == "applied"
checks.append("explicit formal adoption and identical retry creates only one trip")
trip_id = operation["target_trip_id"]
days = api("/trips/" + trip_id + "/days")
assert len(days[0]["activities"]) == 2
execution = api("/trips/" + trip_id + "/execution/start", "POST", {"day_plan_id": days[0]["id"]})
for action in ["arrive", "start_activity", "complete"]:
    execution = api("/trip-executions/" + execution["id"] + "/actions", "POST", {"action": action, "activity_id": days[0]["activities"][0]["id"]})
progress = api("/trips/" + trip_id + "/execution-progress")
checks.append("formal schedule and manual execution advance")
session = api("/assistant/sessions", "POST", {})
answer = api("/assistant/sessions/" + session["id"] + "/messages", "POST", {"message": "旅行前整理行李时有哪些通用注意事项？不要修改任何旅行。", "message_id": str(uuid4())})
assert answer["messages"][-1]["assistant"]
checks.append("real model unified assistant response")
print(json.dumps({"checks": checks, "environment": "official-backup rehearsal only", "formal_status": operation["status"], "real_route": True}, ensure_ascii=False, indent=2))
