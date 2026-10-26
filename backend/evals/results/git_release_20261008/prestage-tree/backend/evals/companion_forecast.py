"""Forecast integration evaluation. --live uses real providers; no fake fallback."""
import argparse, asyncio, json, runpy, time
from pathlib import Path
from datetime import UTC, datetime
from collections import Counter
from app.companion_facts import CompanionFactAdapter
from app.companion_runtime import CompanionRuntime
from app.companion_provider import ModelCompanionProvider
from app.companion_knowledge import build_reviewed_knowledge_tool
from app.travel_goal_router import route_travel_goal
from evals.companion_phase2.run import Reader, CountingTool, CountingProvider
from evals.phase25_final import snapshot

CASES=[
 ("basic","杭州明天下午天气怎么样？","success",True),
 ("rain","杭州明天会下雨吗？","success",True),
 ("explicit","10月2日下午南京天气如何？","success",True),
 ("context","明天下午天气怎么样？","success",True),
 ("district","西湖区明天天气怎么样？","success",False),
 ("mixed","西湖有什么历史文化特色，明天下午天气怎么样？","success",True),
 ("timeout","杭州明天下午天气怎么样？","timeout",True),
 ("current","杭州现在多少度？","success",False),
 ("past","杭州昨天下午下雨了吗？","success",False),
 ("tomorrow_evening","南京明天晚上天气怎么样？","success",True),
 ("day_after","后天下午西湖附近天气如何？","success",True),
 ("outdoor","南京明天上午适合户外活动吗，天气如何？","success",True),
 ("malformed","杭州明天下午天气？","malformed",True),
 ("empty","杭州明天下午天气？","empty",True),
 ("5xx","杭州明天下午天气？","5xx",True),
 ("stale","杭州明天下午天气？","stale",True),
 ("location_failure","杭州明天下午天气？","location_failed",True),
 ("missing_date","杭州天气如何？","success",False),
 ("knowledge","根据可靠资料讲讲西湖历史。","success",False),
 ("planning","帮我规划南京三天","success",False),
]
class CountFacts:
    def __init__(self,tool): self.tool,self.plans,self.calls=tool,[],[]
    async def plan_forecast(self,*args):
        p=await self.tool.plan_forecast(*args);self.plans.append(p);return p
    async def resolve_facts(self,requirements):
        self.calls.extend(requirements);return await self.tool.resolve_facts(requirements)

async def run(live=False):
    out=Path(__file__).parent/'results/travel_facts_integration';out.mkdir(parents=True,exist_ok=True)
    fixtures=runpy.run_path(str(Path(__file__).resolve().parents[1]/'tests/test_companion_facts.py')) if not live else None
    realtool=CompanionFactAdapter() if live else None
    rows=[]
    for cid,text,mode,expected in CASES:
        # Fault-injection scenarios are reported separately offline, not disguised as live observations.
        if live and mode!='success': continue
        tool=realtool if live else fixtures['tool_fixture'](mode)[0]
        fact=CountFacts(tool);knowledge=CountingTool(await build_reviewed_knowledge_tool())
        provider=ModelCompanionProvider() if live else fixtures['NoModel']()
        counted=CountingProvider(provider);goal=route_travel_goal(text)
        messages=[{"id":"prior","user":"我准备去南京。","assistant":""}] if cid=='context' else []
        start=time.perf_counter();result=None;error=None
        if goal.target_runtime=='companion':
            try: result=await CompanionRuntime(Reader(),counted,knowledge,fact).run(session_id='forecast-eval',turn_id=cid,message=text,goal=goal,messages=messages)
            except Exception as exc: error=type(exc).__name__
        rows.append({'case_id':cid,'text':text,'fault_injection':None if live else mode,'expected_fact_call':expected,'runtime':goal.target_runtime,
            'mutation_requested':goal.mutation_requested,'fact_calls':len(fact.calls),'knowledge_calls':len(knowledge.calls),'planning_calls':0,
            'model_calls':counted.calls,'provider_observations':getattr(provider,'observations',[]),'result':result.model_dump(mode='json') if result else None,
            'latency_seconds':round(time.perf_counter()-start,3),'error':error,
            'checks':{'tool_selection':bool(fact.calls)==expected,'planning_authorization_error':goal.target_runtime!='companion' if cid!='planning' else goal.target_runtime!='planning',
                'stale_published':bool(result and any(not r.usable_as_current for r in result.resolved_facts) and '预计气温' in result.response_text and not any(r.usable_as_current for r in result.resolved_facts)),
                'unsupported_dynamic_claim':bool(result and '预计气温' in result.response_text and not any(r.usable_as_current for r in result.resolved_facts)),
                'natural_prose':bool(result and not any(x in result.response_text for x in ['FactRequirement','ResolvedFact','provider_prediction','freshness_status','fact_id'])),
                'mixed_success':bool(result and result.claims and any(r.usable_as_current for r in result.resolved_facts)) if cid=='mixed' else None}})
    positive=[x for x in rows if x['expected_fact_call']];called=[x for x in rows if x['fact_calls']]
    summary={'cases':len(rows),'errors':sum(x['error'] is not None for x in rows),'fact_tool_precision':f"{sum(x['expected_fact_call'] for x in called)}/{len(called)}",
        'fact_tool_recall':f"{sum(bool(x['fact_calls']) for x in positive)}/{len(positive)}",'unnecessary_fact_calls':sum(bool(x['fact_calls']) and not x['expected_fact_call'] for x in rows),
        'planning_authorization_errors':sum(x['checks']['planning_authorization_error'] for x in rows),'stale_fact_usage':sum(x['checks']['stale_published'] for x in rows),
        'unsupported_dynamic_claim_count':sum(x['checks']['unsupported_dynamic_claim'] for x in rows),'natural_answers':sum(x['checks']['natural_prose'] for x in rows),
        'actual_model_calls':sum(x['model_calls'] for x in rows),'resolved_statuses':dict(Counter(r['resolution_status'] for x in rows if x['result'] for r in x['result']['resolved_facts']))}
    payload={'measured_at':datetime.now(UTC).isoformat(),'live_provider':live,'snapshot':snapshot(),'summary':summary,'cases':rows,
        'metric_limits':'Exact tool intent checks and server rendering checks, not independent weather-accuracy or general factuality audit. Planning row routes only; persistence safety separately tested. Model provider installed in live runtime but forecast paths need no generation.'}
    (out/('real_companion.json' if live else 'companion_eval.json')).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');args=p.parse_args();asyncio.run(run(args.live))
