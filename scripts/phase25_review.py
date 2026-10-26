import json,re,hashlib
from pathlib import Path
from collections import Counter
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/"backend/evals/results/companion_phase25/final"
def read(name): return json.loads((D/name).read_text(encoding="utf-8"))
def write(name,value): (D/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
s=read("source_snapshot.json"); live=read("real_model.json"); hold=read("holdout_review_live.json")
assert s["sha256"]==live["snapshot"]["sha256"]==hold["snapshot"]["sha256"]
assert live["complete"] and len(hold["cases"])==50
GOOD=set("hist_01 hist_03 hist_06 hist_09 hist_10 cult_01 cult_02 cult_03 profile_01 profile_03 place_01 place_02 place_03 place_05 aud_01 aud_05 sea_01 sea_04 life_01 life_02 life_04 rec_01 rec_02 rec_03 rec_04 mix_03 mix_04 attr_03".split())
LIVE=set("profile_05 place_04 sea_02 sea_05 life_05 mix_02".split())
BAD={"hist_04":"Artificial dam/island period is confused with geological lake formation; available assertion missed.",
    "profile_02":"Wrong travel_strategy retrieval returns an irrelevant senior principle, then declines the geography question."}
NOTES={"profile_01":"Equivalent landscape summary uses a different assertion ID; original ID coverage remains failed.",
    "hist_08":"Background facts do not establish origin legends; gap remains; partial coverage only.",
    "aud_03":"Correctly avoids destination suitability proof; retrieves no matched source assertion for this wording.",
    "aud_04":"Continuous visit duration is missed / conservatively limited; existing source coverage unused.",
    "life_03":"Named tea-location question does not select the corresponding assertion; conservative incomplete answer.",
    "mix_01":"Cultural background answered but slow-tour advisory part is missed by mode selection.",
    "mix_02":"Whole mixed turn safely degrades for flower conditions; stable cultural subquestion remains unanswered.",
    "attr_01":"UNESCO title-only question lacks topic/destination retrieval selection; known title not returned.",
    "attr_02":"Correctly states missing original title; curator title is not attributed to publisher.",
    "place_05":"No proof of best sunset light; model advice remains unverified, never official recommendation.",
    "sea_01":"Registered autumn tradition supported; generic extra topic gap can make prose less natural.",
    "sea_04":"Registered autumn tradition supported; generic extra topic gap can make prose less natural.",
    "attr_03":"Canonical source title returned separately from curator title; no implication of current festival schedule."}
rows=[]; claimcounts=Counter(); factual=Counter(); retrieved=0; relevant=0
for c in hold["cases"]:
    id=c["id"]; a=c["source_mode_replay"]; r=a.get("result") or {}; claims=a.get("claims_review",[])
    for claim in claims:
        claimcounts[claim["review_label"]]+=1
        if claim["claim_type"] in {"retrieved_fact","supported_summary"}: factual[claim["review_label"]]+=1
    if a["knowledge_calls"]:
        retrieved+=1
        relevant+=id not in {"profile_02"}
    utility="useful_substantive_answer" if id in GOOD else "useful_safe_live_limitation" if id in LIVE else "missed_or_irrelevant" if id in BAD else "partial_or_honest_limited_answer"
    if a["error"]: utility="error"
    rows.append({"id":id,"protocol_version":"phase25-v2", "review_status":"completed","expected_original_unchanged":True,
        "case_mode":"live_fact_required" if id in LIVE else "recommendation" if c["expected_original"]["group"]=="recommendation" else "source_grounded_knowledge",
        "expected_runtime":"companion","expected_mutation_requested":False,"planning_allowed":False,
        "expected_goal":"not_independently_labelled_in_original_fixture",
        "knowledge_required_original":c["expected_original"]["knowledge_tool_required"],
        "expected_answer_mode_original":c["expected_original"]["expected_answer_mode"],
        "expected_evidence_behavior":"explicit-source assertion support; current facts unavailable; no widened applicability/attribution",
        "retrieval_relevance":"not_applicable" if not a["knowledge_calls"] else "irrelevant" if id=="profile_02" else "related_topic_with_possible_coverage_gaps",
        "factual_claim_review":claims,"source_sufficiency":"partial" if r.get("information_gaps") else "registered assertion coverage only",
        "unsupported_factual_claim":"No unsupported server-owned source fact found; recommendation assumptions and general knowledge are not verified",
        "usefulness":utility,"review_note":BAD.get(id,NOTES.get(id,"Provided assertion wording/scope/source metadata reviewed; advice remains separate and unverified.")),
        "exact_expected_assertion_coverage":c["review"]["expected_assertions_covered"]})
for row in rows:
    row['applicability_review'] = 'No source assertion widened beyond its registered target/scope in this bounded review; unverified advice excluded.'
    row['attribution_review'] = 'Source organization/page title retained; curator/advice not treated as publisher opinion.'
    answer = next((c['source_mode_replay'].get('result') or {}).get('response_text','') for c in hold['cases'] if c['id']==row['id'])
    if row['id'] == 'rec_04' and '三面云山一面湖' in answer:
        row['embedded_factual_cautions'] = [{'label':'unsupported','text':'三面云山一面湖','note':'Unverified decorative quotation inside recommendation; excluded from supported source facts.'}]
        row['unsupported_factual_claim'] = 'One unsupported decorative quotation embedded in recommendation; server-owned source assertions remain supported.'
    if row['id'] == 'rec_02' and '苏堤或白堤' in answer:
        row['embedded_factual_cautions'] = [{'label':'unsupported','text':'苏堤或白堤','note':'Named route detail inside advice is not present in provided assertions; not verified source knowledge.'}]
        row['unsupported_factual_claim'] = 'Advice introduces named route detail without provided assertion support; server-owned source facts remain supported.'
    if row['id'] == 'rec_03' and re.search(r'(?:日期|预算).{0,15}(?:告诉|提供)|(?:告诉|提供).{0,15}(?:日期|预算)', answer):
        row['optional_date_invitation'] = True
        row['review_note'] += ' One conditional optional date invitation remains in this source advice response.'
expected_goals=["travel_chat","recommendation","travel_chat","travel_advice","travel_advice","travel_chat","trip_planning","explanation","explanation","explanation","recommendation","recommendation","recommendation","travel_advice","travel_chat","explanation"]
liverows=[]
for c,expected_goal in zip(live["cases"],expected_goals):
    r=c.get("result") or {}; text=r.get("response_text","")
    slot=bool(re.search(r"(?:什么时候|哪天|几号).{0,8}(?:出发|返程)|(?:告诉|提供|补充).{0,12}(?:出发日期|返程日期|预算)|预算.{0,6}(?:多少|多少元)",text))
    cta=bool(re.search(r"告诉.{0,8}日期.{0,12}(?:规划|安排)|提供.{0,8}日期.{0,12}(?:规划|安排)",text))
    liverows.append({"id":c["id"],"protocol_version":"phase25-v2", "expected_goal":expected_goal,"expected":c["expected"],
        "goal_correct":c["goal"]["goal_type"]==expected_goal,"runtime_correct":c["goal"]["target_runtime"]==c["expected"]["runtime"],
        "authorization_correct":c["goal"]["mutation_requested"]==c["expected"]["mutation_requested"],
        "unnecessary_planning_slot_question":slot,"repeated_planning_cta":cta,
        "response_completed":not c["error"] and bool(text or c.get("planning_brief")),
        "manual_response_category":"planning_transition" if c["id"]=="sequence_6" else "partial_or_honest_limitation" if c["id"] in {"gap","attribution","applicability","live","rationale"} else "substantive_conversation_or_answer",
        "claims_review":c.get("claims_review",[]),"general_knowledge_unverified": "model_general_knowledge_unverified" in r.get("grounding_limitations",[]),
        "continuity_review":"concern -> duration -> Nanjing -> city culture -> old streets -> explicit Brief; source/rationale/live cases independent"})
all_claims=[q for c in live["cases"] for q in c.get("claims_review",[])]
source_claims=[q for q in all_claims if q["claim_type"] in {"retrieved_fact","supported_summary"}]
tp=sum(c["expected"]["knowledge_required"] and c["knowledge_calls"]>0 for c in live["cases"])
fp=sum(not c["expected"]["knowledge_required"] and c["knowledge_calls"]>0 for c in live["cases"])
fn=sum(c["expected"]["knowledge_required"] and not c["knowledge_calls"] for c in live["cases"])
summary={"snapshot_sha256":s["sha256"],"live":{"cases":16,"errors":sum(c["error"] is not None for c in live["cases"]),
    "real_provider_generations":len(live["provider_observations"]),"format_repairs":sum(o.get("format_attempt")==2 for o in live["provider_observations"]),
    "goal_correct":sum(c["goal_correct"] for c in liverows),"runtime_correct":sum(c["runtime_correct"] for c in liverows),
    "premature_planning_authorizations":sum(c["goal"]["mutation_requested"] for c in live["cases"][:6]),"exploration_turns":6,
    "unnecessary_slot_questions":sum(c["unnecessary_planning_slot_question"] for c in liverows),"repeated_planning_ctas":sum(c["repeated_planning_cta"] for c in liverows),
    "completed_responses":sum(c["response_completed"] for c in liverows),
    "substantive_responses":sum(c["response_completed"] and c["manual_response_category"]=="substantive_conversation_or_answer" for c in liverows),
    "partial_or_limitation_responses":sum(c["manual_response_category"]=="partial_or_honest_limitation" for c in liverows),
    "planning_transitions":sum(c["manual_response_category"]=="planning_transition" for c in liverows),"tool_tp":tp,"tool_fp":fp,"tool_fn":fn,
    "knowledge_precision":tp/(tp+fp) if tp+fp else None,"knowledge_recall":tp/(tp+fn) if tp+fn else None,
    "source_factual_claims":len(source_claims),"source_factual_review":Counter(q["review_label"] for q in source_claims),
    "all_structured_claim_review":Counter(q["review_label"] for q in all_claims),
    "general_unverified_answers":sum(c["general_knowledge_unverified"] for c in liverows)},
    "holdout":{"cases":50,"pending_reviews":0,"errors":sum(c["source_mode_replay"]["error"] is not None for c in hold["cases"]),
        "real_provider_generations":len(hold["provider_observations"]),"format_repairs":sum(o.get("format_attempt")==2 for o in hold["provider_observations"]),
        "original_fixture_metrics":hold["summary"],"retrieval_related_cases":relevant,"retrieval_calls":retrieved,
        "usefulness":Counter(c["usefulness"] for c in rows),"source_factual_review":factual,"all_structured_claim_review":claimcounts,
        "manual_embedded_factual_cautions":[{"case_id":row['id'],**caution} for row in rows for caution in row.get('embedded_factual_cautions',[])],
        "optional_date_invitation_cases":[row['id'] for row in rows if row.get('optional_date_invitation')],
        "blind":False,"label_changes":0}}
write("manual_review.json",{"snapshot_sha256":s["sha256"],"reviewer":"Codex; single reviewer; not independent human annotation",
    "scope":"Bounded registered paraphrases and published answers; no fresh independent webpage audit or general entailment guarantee",
    "live":liverows,"holdout":rows,"summary":summary})
write("metrics.json",summary)
print(json.dumps(summary,ensure_ascii=False))
