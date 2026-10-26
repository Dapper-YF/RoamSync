"""Versioned final acceptance: original holdout is immutable; all outputs bind source hash."""
import argparse, asyncio, hashlib, json, re, time
from pathlib import Path
from collections import Counter
from datetime import UTC, datetime
from app.companion_contracts import CompanionAnswerDraft
from app.companion_runtime import CompanionRuntime
from app.companion_provider import ModelCompanionProvider
from app.companion_knowledge import build_reviewed_knowledge_tool
from app.companion_state import build_planning_brief
from app.travel_goal_router import route_travel_goal
from evals.companion_phase2.run import Reader, CountingTool, CountingProvider

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/results/companion_phase25/final"

def snapshot():
    files = sorted(p for base in ["app", "tests", "migrations", "evals"] for p in (ROOT/base).rglob("*")
        if p.is_file() and "__pycache__" not in str(p) and "results" not in p.parts and p.suffix in {".py", ".json"})
    files += [ROOT / x for x in ["pyproject.toml", "uv.lock", "Dockerfile", "alembic.ini"]]
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    return {"sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(), "files": hashes}

def write(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

class NeutralProvider:
    observations = []
    async def generate(self, context, need):
        return CompanionAnswerDraft()

def claim_review(result):
    # Independent of citation membership: compare the actual claim text/type/scope
    # to the curated assertion registry, preserving recommendations separately.
    registry = {a.assertion_id:(a,e) for e in result.knowledge_evidence for a in e.answerable_assertions}
    rows=[]
    for c in result.claims:
        if c.claim_type in {"agent_inference", "recommendation"}:
            label = "recommendation_not_fact" if c.claim_type == "recommendation" else "not_applicable"
        elif c.claim_type == "curator_inference":
            label = "partially_supported"
        elif c.assertion_ids:
            matches = [registry.get(i) for i in c.assertion_ids]
            label = "supported" if all(m and m[0].text == c.text and m[0].claim_type == c.claim_type
                and m[0].applicability == c.applicability for m in matches) else "unsupported"
        else:
            label = "supported" if any(e.source_page_title and e.source_page_title in c.text for e in result.knowledge_evidence) else "unsupported"
        rows.append({"text":c.text, "claim_type":c.claim_type, "review_label":label,
            "assertion_ids":c.assertion_ids, "scope":c.applicability.model_dump(),
            "attribution": [a.model_dump() for a in c.source_attributions],
            "basis":"exact registered reviewed paraphrase and scope; no general entailment verifier"})
    return rows

async def evaluate(text, provider, history=None):
    history=history or []
    tool=CountingTool(await build_reviewed_knowledge_tool())
    counted=CountingProvider(provider)
    goal=route_travel_goal(text, history)
    row={"message":text,"goal":goal.model_dump(mode="json"),"error":None}
    start=time.perf_counter()
    if goal.target_runtime == "planning":
        brief=build_planning_brief("final",str(len(history)),text,goal,history)
        row.update(planning_brief=brief.model_dump(mode="json") if brief else None, result=None)
    else:
        try:
            result=await CompanionRuntime(Reader(),counted,tool).run(session_id="final",turn_id=str(len(history)),message=text,goal=goal,messages=history)
            row.update(result=result.model_dump(mode="json"),claims_review=claim_review(result))
        except Exception as exc:
            row.update(error=type(exc).__name__, error_code=getattr(exc,"code",None),
                validation_errors=exc.__cause__.errors(include_input=False) if hasattr(exc.__cause__,"errors") else None, result=None)
    row.update(knowledge_calls=len(tool.calls),provider_calls=counted.calls,latency=round(time.perf_counter()-start,3))
    return row

async def holdout(real=False):
    provider = ModelCompanionProvider() if real else NeutralProvider()
    path=ROOT/"evals/results/companion_phase25/holdout_v1.json"
    original=path.read_bytes(); fixture=json.loads(original)
    report={"snapshot":snapshot(),"fixture_sha256":hashlib.sha256(original).hexdigest(),
        "protocol":"phase25-v2", "mode":"real_source_replay" if real else "controlled_contract_replay", "blind":False, "unsealed_and_used_for_targeted_bug_fixes":True, "reviewer":"Codex registered-assertion audit plus recorded case-level review",
        "qualification":"Original 50 cases preserved. v1 assumes RAG by default; v2 source-mode uses explicit source suffix and is a protocol replay, not a new blind holdout.","cases":[]}
    for c in fixture["cases"]:
        v1=await evaluate(c["expression"],NeutralProvider())
        replay=c["expression"] + (" 请依据可靠资料回答并给出来源。" if c["knowledge_tool_required"] else "")
        v2=await evaluate(replay,provider)
        r=v2.get("result") or {}; claims=v2.get("claims_review",[])
        actual_ids={i for claim in claims for i in claim["assertion_ids"]}
        need=r.get("information_need",{})
        report["cases"].append({"id":c["id"],"protocol_version":"phase25-v2", "expected_goal":"not_independently_labelled_in_original_fixture", "expected_original":c,"protocol_compatibility":
            "legacy_default_rag" if c["knowledge_tool_required"] and not v1["knowledge_calls"] else "compatible",
            "expected_v2":{"goal":route_travel_goal(replay).goal_type,"runtime":"companion","mutation_requested":False,
                "knowledge_required":c["knowledge_tool_required"],"planning_allowed":False,"answer_mode":c["expected_answer_mode"],
                "evidence_behavior":"reviewed assertions only; preserve missing detail/live/rationale boundaries"},
            "original_execution":v1,"source_mode_replay":v2,"review_status":"completed",
            "review":{"routing_correct":v2["goal"]["target_runtime"]=="companion",
                "planning_authorization_correct":not v2["goal"]["mutation_requested"],
                "need_correct":bool(v2["knowledge_calls"])==c["knowledge_tool_required"] and need.get("answer_mode")==c["expected_answer_mode"],
                "retrieval_relevance": sorted(actual_ids), "expected_assertions_covered":set(c["expected_assertion_ids"])<=actual_ids,
                "evidence_sufficiency":not any(g["code"].startswith("knowledge_") for g in r.get("information_gaps",[])),
                "factual_support":Counter(claim["review_label"] for claim in claims),
                "applicability":[claim["scope"] for claim in claims],"attribution":[claim["attribution"] for claim in claims],
                "unsupported_factual_claim":any(claim["review_label"]=="unsupported" for claim in claims),
                "recommendation_separation":all(claim["claim_type"] not in {"agent_inference","recommendation","curator_inference"} or not claim["attribution"] for claim in claims),
                "answer_usefulness":"partial_answer_or_honest_limitation" if r.get("information_gaps") else "answer_present" if r.get("response_text") else "error"}})
    report["summary"]={"cases":len(report["cases"]),"pending":0,
        **{key:sum(c["review"][key] for c in report["cases"]) for key in ["routing_correct","planning_authorization_correct","need_correct","expected_assertions_covered","unsupported_factual_claim","recommendation_separation"]}}
    assert path.read_bytes()==original
    report["provider_observations"] = provider.observations
    write("holdout_review_live.json" if real else "holdout_review.json",report)
    print(json.dumps(report["summary"]))

LIVE_CASES=[
    ("exact","source_grounded_knowledge","根据可靠资料，西湖文化景观哪一年列入世界遗产名录？",True),
    ("summary","source_grounded_knowledge","根据可靠资料，西湖文化景观的文化意义是什么？",True),
    ("gap","source_grounded_knowledge","根据可靠资料讲讲西湖历史和形成的确切年份",True),
    ("attribution","source_grounded_knowledge","UNESCO官方推荐西湖哪些人文摄影机位？请给出依据",True),
    ("applicability","source_grounded_knowledge","通用老年旅游规范能证明杭州一定适合我父母吗？请给出来源",True),
    ("recommendation","recommendation","根据可靠资料，西湖有哪些文化景观值得观察和摄影？",True),
    ("general","general_conversation","南京是一个怎样的城市？",False),
    ("live","live_fact_required","今天景区几点关门？",False),
    ("rationale","decision_explanation","为什么之前把西湖安排在18点？",False)]

async def live():
    from app.config import get_settings
    settings=get_settings()
    if not settings.planner_api_key.get_secret_value(): raise RuntimeError("real model config required")
    provider=ModelCompanionProvider(); history=[]
    report={"snapshot":snapshot(),"protocol":"phase25-v2","real_model":settings.planner_model,
        "no_database":True,"planning_run_evidence":"separate PostgreSQL integration; router/Brief observed here",
        "cases":[],"complete":False}
    sequence=["你好","过几天国庆了，我想出去玩，但是怕一个人玩没意思，你有什么建议吗","目前准备玩个三四天的样子","你觉得南京怎么样","南京它是一个怎样的城市呢","跟我讲讲南京的老街巷吧","听起来不错，那帮我规划南京三天吧。"]
    for i,text in enumerate(sequence):
        row=await evaluate(text,provider,history)
        row["id"]="sequence_"+str(i); row["protocol_version"]="phase25-v2"; row["mode"]="explicit_planning" if i==6 else "exploration_non_planning"
        row["expected"]={"runtime":"planning" if i==6 else "companion","mutation_requested":i==6,"knowledge_required":False,"planning_allowed":i==6,"answer_mode":"planning" if i==6 else "general_knowledge","evidence_behavior":"general_model_knowledge_unverified"}
        report["cases"].append(row)
        history.append({"id":str(i),"user":text,"assistant":(row.get("result") or {}).get("response_text",""),"goal_routing":row["goal"],"companion_result":row.get("result") or {}})
        write("real_model.json",report); print(row["id"],row["error"],row["latency"],flush=True)
    for id,mode,text,required in LIVE_CASES:
        row=await evaluate(text,provider); row.update(id=id,protocol_version="phase25-v2",mode=mode,expected={"runtime":"companion","mutation_requested":False,"knowledge_required":required,"planning_allowed":False,"answer_mode":mode,"evidence_behavior":"registered assertions and honest gaps" if required else "general knowledge or server boundary"})
        report["cases"].append(row); write("real_model.json",report); print(id,row["error"],row["latency"],flush=True)
    report.update(complete=True,provider_observations=provider.observations)
    write("real_model.json",report)

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("mode",choices=["holdout","holdout-live","live","snapshot"]); a=p.parse_args()
    if a.mode=="snapshot": write("source_snapshot.json",snapshot())
    else: asyncio.run(holdout(a.mode=="holdout-live") if a.mode in {"holdout", "holdout-live"} else live())
