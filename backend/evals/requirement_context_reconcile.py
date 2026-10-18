"""Finish reads on the already accepted fresh fixture; do not repeat Accept."""
import json
import os
import urllib.request
from pathlib import Path

assert os.environ.get("ROAMSYNC_ISOLATED_INTEGRATION") == "1"
assert os.environ["DATABASE_URL"].endswith("/roamsync_v2_integration")
prior = json.loads(Path("/tmp/b-context-result.json").read_text())
assert prior["decision"]["run"]["status"] == "accepted"
trip_id = prior["trip_id"]
headers = {"X-RoamSync-Access": os.environ["ROAMSYNC_INTEGRATION_TOKEN"], "Content-Type": "application/json"}


def api(path, body=None):
    req = urllib.request.Request("http://127.0.0.1:8000/api/v1" + path,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.loads(response.read())


current = api("/trips/" + trip_id + "/planning-context")
assert current["trip"]["title"].startswith("B 多轮背景与保护验收 ")
before = prior["revision"]["before_snapshot"]
out = {"scope": "readback of already accepted labelled B fixture; no repeat Accept", "trip_id": trip_id,
       "run_id": prior["run_id"], "source_evidence": "live-final.json", "checks": [], "metadata_changes": {}}
assert current["days"][1]["activities"][0]["duration_minutes"] == 45
assert current["trip"]["version"] == before["trip"]["version"] + 1
for index in (0, 2):
    original = before["days"][index]["activities"][0]
    actual = current["days"][index]["activities"][0]
    changes = {key: [original[key], value] for key, value in actual.items() if original[key] != value}
    assert not (changes.keys() - {"version", "updated_at"}), changes
    out["metadata_changes"][str(index + 1)] = changes
requirements = api("/trips/" + trip_id + "/requirements")
legacy = next(r for r in requirements["records"] if r["text"] == "此次验收未实际到访")
assert all(legacy["id"] not in [r["id"] for r in rows] for rows in requirements["effective_by_date"].values())
assert legacy["status"] == "active"  # raw history preserved, not a data cleanup
out["checks"].append("Accepted version advanced once; day2 is 45min; day1/day3 identity/schedule/cost/lock semantics preserved; metadata touches disclosed")
out["checks"].append("Legacy background record still persisted, excluded from effective projection after Accept")
out["unbound_pronoun_resolution"] = api("/trips/" + trip_id + "/planning-intent/resolve",
    {"message": "把它改成45分钟，其他日期不要动"})
assert out["unbound_pronoun_resolution"]["requires_clarification"]
assert not out["unbound_pronoun_resolution"]["grounded_intent"]["unresolved_place_mentions"]
assert all(not op["place_mentions"] for op in out["unbound_pronoun_resolution"]["semantic_draft"]["operations"])
out["checks"].append("Unbound cross-turn pronoun requires identity clarification without treating duration as a place")
target = current["days"][1]
out["bound_pronoun_resolution"] = api("/trips/" + trip_id + "/planning-intent/resolve",
    {"message": "把它改成45分钟，其他日期不要动", "selected_day_id": target["id"],
     "selected_activity_id": target["activities"][0]["id"]})
bound = out["bound_pronoun_resolution"]
assert not bound["requires_clarification"]
assert bound["grounded_intent"]["target_activity_ids"] == [target["activities"][0]["id"]]
assert not bound["grounded_intent"]["unresolved_place_mentions"]
out["checks"].append("Explicit UI activity binding resolves pronoun to the same activity without new place lookup")
out["before_trip_version"] = before["trip"]["version"]
out["after_trip_version"] = current["trip"]["version"]
out["status"] = "passed"
print(json.dumps(out, ensure_ascii=False, indent=2))
