"""Run inside rebuilt production API. Uses a separate synthetic session; no reset/approval."""
import asyncio, hashlib, json, uuid, urllib.request
from pathlib import Path
from sqlalchemy import select, func
from app.database import AssistantSession, PlanningRun, Trip, session_factory

async def state():
    async with session_factory() as db:
        return {"runs":await db.scalar(select(func.count()).select_from(PlanningRun)),
            "trips":await db.scalar(select(func.count()).select_from(Trip)),
            "trip_versions":{str(id):v for id,v in (await db.execute(select(Trip.id,Trip.version))).all()}}

async def setup():
    async with session_factory() as db:
        row=AssistantSession(messages=[], applied_actions={})
        db.add(row); await db.commit(); return str(row.id)

manifest=json.loads(Path("/tmp/source_snapshot.json").read_text())
checks={key:hashlib.sha256((Path("/app")/key).read_bytes()).hexdigest()==value
    for key,value in manifest["files"].items() if not key.startswith("tests/") and key!="Dockerfile"}
assert all(checks.values()), "production source mismatch"
session=asyncio.run(setup()); before=asyncio.run(state())
report={"snapshot_sha256":manifest["sha256"],"runtime_files_verified":len(checks),"runtime_hashes_match":all(checks.values()),
    "synthetic_session_id":session,"cases":[],"before":before,"complete":False}
texts=["你好","国庆想出去但怕一个人无聊","玩三四天","南京怎么样","南京是一个怎样的城市？","根据可靠资料讲讲西湖历史和形成的确切年份","今天这个景区几点关门？","那帮我规划南京三天吧。"]
for i,text in enumerate(texts):
    req=urllib.request.Request("http://127.0.0.1:8000/api/v1/assistant/sessions/"+session+"/messages",
        data=json.dumps({"message":text,"message_id":str(uuid.uuid4())},ensure_ascii=False).encode(),headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=120) as response:
            data=json.load(response); msg=data["messages"][-1]
            row={"message":text,"http_status":response.status,"goal":msg["goal_routing"],"answer":msg["assistant"],
                "planning_brief":msg.get("planning_brief"),"latest_run_id":data["latest_run_id"],"pending_action":bool(data["pending_action"]),
                "companion_result":msg.get("companion_result"),"error":None}
            row["expected_runtime"]="planning" if i==7 else "companion"
            row["correct"]=row["goal"]["target_runtime"]==row["expected_runtime"] and row["goal"]["mutation_requested"]==(i==7)
            if i==4:
                result=row['companion_result'] or {}
                row['general_unverified_no_retrieval']='model_general_knowledge_unverified' in result.get('grounding_limitations',[]) and not result.get('knowledge_evidence')
                row['correct'] &= row['general_unverified_no_retrieval']
            if i==6:
                row['live_safe_limitation']=(row['companion_result'] or {}).get('grounding_status')=='live_verification_required'
                row['correct'] &= row['live_safe_limitation']
    except Exception as exc:
        row={"message":text,"error":type(exc).__name__,"correct":False}
    report["cases"].append(row)
    Path("/tmp/production_smoke.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(i,row["correct"],row["error"],flush=True)
report["after"]=asyncio.run(state()); report["complete"]=True
report["formal_state_unchanged"]=before==report["after"]
Path("/tmp/production_smoke.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
assert all(r["correct"] for r in report["cases"]) and report["formal_state_unchanged"]
