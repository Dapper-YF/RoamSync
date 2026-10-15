"""Join completed anonymous ratings; report comparable dimensions and raw costs."""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

from app.companion_state import build_planning_brief
from app.travel_goal_router import route_travel_goal
from evals.companion_blind_review import DIMENSIONS


def analyze(directory):
    packet={r["blind_id"]:r for r in json.loads((directory/"blind/blind_packet.json").read_text(encoding="utf-8"))}
    ratings={r["blind_id"]:r for r in json.loads((directory/"blind/ratings.json").read_text(encoding="utf-8"))["ratings"]}
    key=json.loads((directory/"blind/blind_key.json").read_text(encoding="utf-8"))
    assert set(packet)==set(ratings)=={r["blind_id"] for r in key}
    joined=[]
    for item in key:
        rating=ratings[item["blind_id"]]
        assert all(v is None or isinstance(v,int) and 1<=v<=5 for v in rating["scores"].values())
        joined.append({**item,**packet[item["blind_id"]],**rating})
    (directory/"review_unblinded.json").write_text(json.dumps(joined,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    summary={"quality":{},"cost":{},"limitations":["Single reviewer, not independent human double-blind",
        "No score for failed outputs or formal planning", "Accuracy is null when substantive facts await verification",
        "Matched triplets per dimension only; no overall ranking", "One run, fixed sequential A/B/C order, no statistical significance"]}
    for filename in ("fixed18_real.json","holdout_real.json"):
        report=json.loads((directory/filename).read_text(encoding="utf-8"))
        groups=defaultdict(dict)
        for row in joined:
            if row["file"]==filename:
                groups[row["case_id"]][row["mode"]]=row
        complete={cid:g for cid,g in groups.items() if set(g)=={"A","B","C"}}
        summary["quality"][filename]={"matched_cases":len(complete),"excluded_incomplete_cases":list(set(groups)-set(complete)),"dimensions":{}}
        for dimension in DIMENSIONS:
            eligible={cid:g for cid,g in complete.items() if all(r["scores"][dimension] is not None for r in g.values())}
            summary["quality"][filename]["dimensions"][dimension]={"matched_cases":len(eligible),
                "means":{m:mean(g[m]["scores"][dimension] for g in eligible.values()) if eligible else None for m in "ABC"},
                "case_ids":list(eligible)}
        summary["cost"][filename]={}
        for mode in "ABC":
            rows=[r for r in report["rows"] if r["mode"]==mode and r["goal"]["target_runtime"]=="companion"]
            observations=[o for r in rows for o in r["model_observations"]]
            usage=[o["usage"] for o in observations if o.get("usage")]
            latencies=sorted(r["latency_seconds"] for r in rows)
            generated=[r["latency_seconds"] for r in rows if r["model_calls"] and not r["error"]]
            summary["cost"][filename][mode]={"companion_cases":len(rows),"errors":sum(bool(r["error"]) for r in rows),
                "rag_calls":sum(r["rag_calls"] for r in rows),"model_calls":len(observations),
                "known_prompt_tokens":sum(u["prompt_tokens"] for u in usage),
                "known_completion_tokens":sum(u["completion_tokens"] for u in usage),
                "known_total_tokens":sum(u["total_tokens"] for u in usage),
                "unknown_usage_calls":sum(o.get("usage") is None for o in observations),
                "mean_seconds":mean(latencies),"median_seconds":median(latencies),
                "max_seconds":max(latencies),"successful_generated_mean_seconds":mean(generated) if generated else None,
                "retrieval_seconds":sum(r["retrieval_seconds"] for r in rows)}
        summary["cost"][filename]["matched_complete_triplets"]={m:{
            "case_count":len(complete),
            "known_total_tokens":sum(r["total_tokens"] or 0 for r in report["rows"]
                if r["mode"]==m and r["case_id"] in complete),
            "mean_seconds":mean(r["latency_seconds"] for r in report["rows"]
                if r["mode"]==m and r["case_id"] in complete)} for m in "ABC"}
    dialogue=json.loads((directory/"dialogue_real.json").read_text(encoding="utf-8"))
    replay=[]
    for row in dialogue["rows"]:
        if row["turn"]!=3:
            continue
        brief=build_planning_brief("quality-dialogue","dialogue-3",row["input"],
            route_travel_goal(row["input"],row["history"]),row["history"])
        checks={"destination_correct":brief.destination=="南京","prepared":brief.status=="prepared",
            "duration":brief.duration_days==3,"preferences_retained":bool(brief.confirmed_preferences),
            "authorization_turn":brief.authorization_turn_id=="dialogue-3"}
        replay.append({"mode":row["mode"],"source":"dialogue_real.json (original saved real histories)",
            "real_model_calls":0,"planning_executed":False,"checks":checks,"brief":brief.model_dump(mode="json")})
    (directory/"handoff_replay_after_fix.json").write_text(json.dumps(replay,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (directory/"comparison_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--directory",type=Path,required=True)
    analyze(parser.parse_args().directory)
