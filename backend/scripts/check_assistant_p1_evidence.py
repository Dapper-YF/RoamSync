"""Check actual P1 execution records, rather than counting HTTP 200 responses."""
import json
import statistics
from pathlib import Path

root=Path(__file__).resolve().parents[2]/"docs/evidence/assistant-p1-20261021"
rows=json.loads((root/"live.json").read_text(encoding="utf-8"))
by={(r["scenario"],r["turn"]):r for r in rows}
def slots(s,t):return by[s,t]["memory"]["slots"]
def prefs(s,t):return " ".join(i["value"] for i in by[s,t]["memory"]["preferences"]+by[s,t]["memory"]["requirements"])
checks={
    "25_complete_no_errors":len(rows)==25 and all(r.get("summary",{}).get("answer_status")=="complete" and not r.get("error") for r in rows),
    "initial_city_and_date":slots("conditions",1).get("city",{}).get("value")=="成都" and slots("conditions",1)["start_date"]["value"]=="2026-11-02",
    "date_duration_replaced":slots("conditions",3)["start_date"]["value"]=="2026-11-05" and slots("conditions",3)["duration_days"]["value"]==3,
    "interest_replaced":"自然" in prefs("conditions",4) and "建筑" not in prefs("conditions",4),
    "city_change_keeps_personal_conditions":slots("conditions",5)["city"]["value"]=="重庆" and slots("conditions",5)["duration_days"]["value"]==3 and "不吃辣" in prefs("conditions",5) and "慢慢逛" in prefs("conditions",5),
    "new_topic_clears_old_conditions":"start_date" not in slots("conditions",7) and not prefs("conditions",7),
    "hypothetical_not_applied":slots("provenance",2)["city"]["value"]=="成都" and slots("provenance",2)["duration_days"]["value"]==4,
    "quoted_instruction_not_applied":slots("provenance",4)["city"]["value"]=="成都" and "不吃辣" in prefs("provenance",4),
    "revocation_and_replacement":"素食" in prefs("provenance",6) and "不吃辣" not in prefs("provenance",6),
    "food_and_architecture_images":all((by["illustrations",t].get("visuals")or{}).get("images") for t in [1,3]),
    "ordinary_and_opted_out_no_image_queries":all(not any(e["stage"]=="images" for e in by["illustrations",t]["summary"]["events"]) for t in [2,4,5]),
    "new_conversation_clears_conditions":not slots("scope",4) and not prefs("scope",4),
    "zero_formal_writes":json.loads((root/"business-counts.json").read_text(encoding="utf-8"))["unchanged"] and all(not r["trip_bound"] and not r["pending_preview"] for r in rows),
}
result={"checks":checks,"all_passed":all(checks.values()),"turns":len(rows),
    "median_ms":statistics.median(r["elapsed_ms"] for r in rows),"max_ms":max(r["elapsed_ms"] for r in rows),
    "image_turns":sum(bool((r.get("visuals")or{}).get("images")) for r in rows),
    "targeted_replay":"scope-recheck/live.json replaces the four earlier scope records; originals retained"}
(root/"live-acceptance.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(result,ensure_ascii=True))
assert result["all_passed"]
