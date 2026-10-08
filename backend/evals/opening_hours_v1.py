"""Real official-source + real Companion graph evaluation; failure injection labelled."""
import asyncio
import json
from pathlib import Path
from datetime import UTC, datetime
from app.companion_facts import CompanionFactAdapter
from app.companion_runtime import CompanionRuntime
from app.companion_contracts import CompanionAnswerDraft
from app.companion_knowledge import build_reviewed_knowledge_tool
from app.travel_goal_router import route_travel_goal
from app.travel_facts.opening_hours import official_gateway
from app.travel_facts.models import FactType
from evals.companion_phase2.run import Reader, CountingTool
from evals.phase25_final import snapshot

OUT=Path(__file__).parent/'results/opening_hours_v1'
CASES=[
 ('nanjing','南京博物院明天几点开门？','opening'),
 ('zhejiang','浙江省博物馆之江馆区明天开放时间？','opening'),
 ('closed','浙江省博物馆之江馆区10月8日开馆吗？','closed'),
 ('monday_exception','南京博物院周一开馆吗？','opening'),
 ('outside_notice','南京博物院10月20日开放吗？','unavailable'),
 ('holiday_uncertain','南京博物院2027年10月2日几点关门？','unavailable'),
 ('unknown_entity','博物馆明天几点开门？','clarify'),
 ('landscape','西湖几点关门？','clarify'),
 ('current','南京博物院现在开着吗？','current'),
 ('unsupported','灵隐寺明天几点开门？','unavailable'),
 ('campus','浙江省博物馆明天几点开门？','clarify'),
 ('source_failed','南京博物院明天几点开门？','failure'),
 ('mixed_weather','南京博物院明天几点开门，南京明天下午天气如何？','mixed'),
 ('weather_only','杭州明天下午天气如何？','weather'),
 ('knowledge_mixed','根据可靠资料讲讲西湖历史，浙江省博物馆之江馆区明天开放时间？','knowledge'),
 ('planning','帮我规划南京三天','planning'),
 ('conflict','南京博物院明天几点开门？','conflict'),
 ('hours_failed_weather_good','南京博物院明天几点开门，南京明天下午天气如何？','hours_failure_mixed'),
 ('weather_failed_hours_good','南京博物院明天几点开门，南京明天下午天气如何？','weather_failure_mixed'),
 ('knowledge_failed_hours_good','根据可靠资料讲讲西湖历史，浙江省博物馆之江馆区明天开放时间？','knowledge_failure'),
]
class NoDynamicModel:
    async def generate(self,*args): raise AssertionError('model cannot generate opening/weather truth')

async def run():
    OUT.mkdir(parents=True,exist_ok=True)
    report={'snapshot':snapshot(),'measured_at':datetime.now(UTC).isoformat(),'cases':[],'complete':False,
            'mode':'real sources and real Companion graph; no DB port; source failure injected in one labelled case'}
    for case_id,message,expected in CASES:
        calls=[]
        async def gateway(provider):
            if expected in ('failure','hours_failure_mixed'):
                calls.append({'provider':provider,'injected_failure':True});raise TimeoutError()
            response=await official_gateway(provider)
            calls.append({'provider':provider,'fetched_at':datetime.now(UTC).isoformat(),'source_found':True})
            return response
        fact=CompanionFactAdapter(opening_gateway=gateway);knowledge=CountingTool(await build_reviewed_knowledge_tool())
        if expected=='weather_failure_mixed':
            async def failed_weather(*args): raise TimeoutError()
            fact.weather_gateway=failed_weather
        if expected=='knowledge_failure':
            async def failed_knowledge(*args): raise TimeoutError()
            knowledge.retrieve=failed_knowledge
        if expected=='conflict':
            # Inject a same-authority disagreement after actual source resolution;
            # explicitly synthetic conflict, not a claim about official publishers.
            original=fact.resolve_facts
            async def conflicting(requirements):
                from app.travel_facts.models import FactBundle,OpeningHoursValue
                from app.travel_facts.resolution import resolve_bundle
                resolved=await original(requirements);result=resolved[0]
                e=result.selected_evidence[0].model_copy(update={'id':'injected-evidence','source_reference':'synthetic:conflict-evaluation'})
                f=result.selected_fact.model_copy(update={'id':'injected-fact','evidence_refs':(e.id,),
                    'value':OpeningHoursValue(closed_all_day=True,local_date=result.value.local_date,timezone=result.value.timezone,schedule_semantics='date_specific_schedule')})
                return [resolve_bundle(requirements[0],FactBundle(facts=(result.selected_fact,f),evidence=(result.selected_evidence[0],e)),fact.freshness,fact.authority,now=datetime.now(UTC))]
            fact.resolve_facts=conflicting
        goal=route_travel_goal(message)
        row={'case_id':case_id,'message':message,'expected':expected,'goal':goal.model_dump(mode='json'),'error':None}
        if expected=='planning': row.update(passed=goal.target_runtime=='planning' and goal.mutation_requested,result=None)
        else:
            try:
                result=await CompanionRuntime(Reader(),NoDynamicModel(),knowledge,fact).run(session_id='opening-real',turn_id=case_id,message=message,goal=goal,messages=[])
                hours=[r for r in result.resolved_facts if r.requirement.fact_type==FactType.OPENING_HOURS]
                weather=[r for r in result.resolved_facts if r.requirement.fact_type==FactType.WEATHER_FORECAST]
                good=bool(hours and all(r.usable_as_current for r in hours))
                passed=goal.target_runtime=='companion' and not goal.mutation_requested and result.planning_handoff is None
                if expected in ('opening','closed','mixed','knowledge','weather_failure_mixed','knowledge_failure'): passed &= good
                if expected=='closed': passed &= bool(hours[0].value.closed_all_day)
                if expected in ('mixed','weather'): passed &= bool(weather and all(r.usable_as_current for r in weather))
                if expected=='weather': passed &= not calls
                if expected=='clarify': passed &= result.status=='needs_clarification' and not calls
                if expected in ('unavailable','current','failure'): passed &= not good
                if expected=='hours_failure_mixed': passed &= not good and bool(weather and all(r.usable_as_current for r in weather))
                if expected=='weather_failure_mixed': passed &= bool(weather and not any(r.usable_as_current for r in weather))
                if expected=='conflict': passed &= bool(hours and hours[0].resolution_status=='conflicting' and not good and '冲突' in result.response_text)
                if expected=='current': passed &= not calls and '不能确认场馆现在' in result.response_text
                if expected=='knowledge': passed &= bool(knowledge.calls and result.claims)
                row.update(result=result.model_dump(mode='json'),passed=bool(passed),source_found=sum(c.get('source_found',False) for c in calls),
                    regular_schedule_resolved=0,date_applicable=sum(r.usable_as_current for r in hours),
                    exception_checked=sum(r.usable_as_current for r in hours),exception_check_scope='reviewed published notice, NOT absence of other closures',
                    final_verified=sum(r.usable_as_current for r in hours))
            except Exception as exc: row.update(error=type(exc).__name__,passed=False,result=None)
        row.update(official_calls=calls,knowledge_calls=len(knowledge.calls));report['cases'].append(row)
        (OUT/'real_companion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(case_id,row['passed'],row.get('error'),flush=True)
    report['complete']=True;report['passed']=all(c['passed'] for c in report['cases'])
    (OUT/'real_companion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    sources=[c for c in report['cases'] if c['case_id'] in ('nanjing','zhejiang')]
    (OUT/'real_source_validation.json').write_text(json.dumps({'snapshot':report['snapshot'],'sources':sources,'passed':all(c['passed'] for c in sources)},ensure_ascii=False,indent=2),encoding='utf-8')
    assert report['passed']

if __name__=='__main__': asyncio.run(run())
