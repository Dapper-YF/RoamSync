"""Immutable-label coverage evaluation. Controlled runs do not measure model creativity."""
import argparse, asyncio, hashlib, json, time
from pathlib import Path
from collections import Counter
from datetime import datetime, UTC
from app.companion_contracts import CompanionAnswerDraft, CompanionDraft
from app.companion_provider import ModelCompanionProvider
from app.companion_runtime import CompanionRuntime
from app.companion_knowledge import build_reviewed_knowledge_tool
from app.travel_goal_router import route_travel_goal
from evals.companion_phase2.run import Reader, CountingTool, CountingProvider
from evals.phase25_final import snapshot, claim_review
OUT=Path(__file__).resolve().parent/'results/knowledge_coverage'
class Neutral:
    async def generate(self,context,need):
        return CompanionDraft(response_text='Controlled general placeholder; not a model quality measurement.') if need.general_knowledge_allowed else CompanionAnswerDraft()
def load(name): return json.loads((OUT/name).read_text(encoding='utf-8'))
def save(name,obj): (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
async def run(mode):
    fixture=load('frozen_v1.json'); manifest=load('freeze_manifest.json')
    assert hashlib.sha256((OUT/'frozen_v1.json').read_bytes()).hexdigest()==manifest['fixture_sha256']
    provider=ModelCompanionProvider() if mode=='real' else Neutral()
    cases=fixture['cases'] if mode!='real' else [c for c in fixture['cases'] if c['case_id'] in fixture['real_model_case_ids']]
    report={'protocol_version':fixture['protocol_version'],'fixture_sha256':manifest['fixture_sha256'],'snapshot':snapshot(),'measured_at':datetime.now(UTC).isoformat(),'mode':mode,'reviewer':'single Codex; exact registered paraphrase/scope plus manual output review; no independent website audit','controlled_provider':mode!='real','cases':[],'complete':False}
    for c in cases:
        tool=CountingTool(await build_reviewed_knowledge_tool()); counted=CountingProvider(provider); goal=route_travel_goal(c['user_text']); start=time.perf_counter(); result=None; error=None
        try:
            result=await CompanionRuntime(Reader(),counted,tool).run(session_id='frozen',turn_id=c['case_id'],message=c['user_text'],goal=goal,messages=[])
        except Exception as exc: error=type(exc).__name__+':'+str(exc)[:250]
        value=result.model_dump(mode='json') if result else {}; need=value.get('information_need',{}); actual_ids={i for q in value.get('claims',[]) for i in q['assertion_ids']}
        expected=set(c['expected_assertion_ids']); equivalence=c.get('assertion_equivalence_groups',[])
        covered=all(i in actual_ids or any(i in g and actual_ids.intersection(g) for g in equivalence) for i in expected)
        topic_ok=set(c['expected_information_need']['requested_topics'])<=set(need.get('requested_fact_topics',[]))
        type_ok=not set(need.get('knowledge_types',[])).intersection(c['forbidden_knowledge_types']) and (not c['knowledge_required'] or bool(set(need.get('knowledge_types',[])).intersection(c['allowed_knowledge_types'])))
        need_ok=topic_ok and need.get('knowledge_required')==c['knowledge_required'] and need.get('live_fact_required')==c['live_fact_required'] and need.get('answer_mode')==c['expected_information_need']['answer_mode']
        review=claim_review(result) if result else []
        fact_claims=[q for q in review if q['claim_type'] in {'retrieved_fact','supported_summary'}]
        has_facts=bool(fact_claims); mixed_ok=bool(has_facts and any(g['code']=='live_fact_unavailable' for g in value.get('information_gaps',[]))) if c['live_fact_required'] and c['knowledge_required'] else None
        missing=bool(expected-actual_ids) and not covered
        utility='not_measured_general' if c['mode']=='general_conversation' and mode!='real' else 'missed_answer' if expected and not covered else 'partial_answer' if covered and c['evidence_sufficiency']=='partial' and has_facts else 'substantive_answer' if has_facts else 'honest_limitation' if value.get('information_gaps') else 'advice_or_unverified_general'
        retrieval='not_applicable' if not c['knowledge_required'] else 'missing' if not tool.calls else 'relevant' if covered and (expected or any(e.get('source_page_title') for e in value.get('knowledge_evidence',[]))) else 'irrelevant_or_insufficient'
        if c['knowledge_required'] and tool.calls and not expected and value.get('knowledge_evidence'): retrieval='related_but_detail_unanswerable'
        row={'case_id':c['case_id'],'expected':c,'goal':goal.model_dump(mode='json'),'result':value,'error':error,'latency':round(time.perf_counter()-start,3),'tool_calls':[x.model_dump(mode='json') for x in tool.calls],'retrieved_results':[x.model_dump(mode='json') for x in tool.results],'provider_calls':counted.calls,'claims_review':review,
            'review':{'runtime_correct':goal.target_runtime==c['expected_runtime'],'authority_correct':goal.mutation_requested==c['expected_mutation_requested'],'need_correct':need_ok,'topic_correct':topic_ok,'type_correct':type_ok,'assertion_coverage':covered if expected else None,'retrieval':retrieval,'mixed_stable_live_coverage':mixed_ok,'utility':utility,'over_refusal':bool(expected and missing and not has_facts),'sufficiency_expected':c['evidence_sufficiency'],'sufficiency_observed':'partial' if has_facts and value.get('information_gaps') else 'sufficient' if has_facts else 'insufficient','natural_prose':not any(x in value.get('response_text','') for x in ['knowledge_','claim_type','资料支持：','模型推断：','资料限制：'])}}
        report['cases'].append(row); save(mode+'_results.json',report)
        if mode=='real': print(c['case_id'],error,flush=True)
    rs=[r['review'] for r in report['cases']]; facts=[q for r in report['cases'] for q in r['claims_review'] if q['claim_type'] in {'retrieved_fact','supported_summary'}]
    report.update(complete=True,provider_observations=getattr(provider,'observations',[]),summary={'cases':len(rs),'errors':sum(r['error'] is not None for r in report['cases']),'runtime_correct':sum(r['runtime_correct'] for r in rs),'authority_correct':sum(r['authority_correct'] for r in rs),'need_correct':sum(r['need_correct'] for r in rs),'type_correct':sum(r['type_correct'] for r in rs),'assertion_covered':sum(r['assertion_coverage'] is True for r in rs),'assertion_cases':sum(r['assertion_coverage'] is not None for r in rs),'retrieval':Counter(r['retrieval'] for r in rs),'mixed_covered':sum(r['mixed_stable_live_coverage'] is True for r in rs),'mixed_cases':sum(r['mixed_stable_live_coverage'] is not None for r in rs),'utility':Counter(r['utility'] for r in rs),'over_refusal':sum(r['over_refusal'] for r in rs),'natural_prose':sum(r['natural_prose'] for r in rs),'source_facts':len(facts),'factual_support':Counter(q['review_label'] for q in facts)})
    save(mode+'_results.json',report);print(json.dumps(report['summary'],ensure_ascii=False))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['baseline','final','real']);args=p.parse_args();asyncio.run(run(args.mode))
