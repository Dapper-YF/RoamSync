"""Bounded real production-provider evaluation; synthetic inputs, no database.

Capture visible JSON only, not reasoning. Persist after every case; filtering
is a separately classified unsuccessful generation, never retry for evasion.
"""
import asyncio
import hashlib
import json
from pathlib import Path
from time import perf_counter
from app.companion_provider import ModelCompanionProvider, GENERAL_KNOWLEDGE_INSTRUCTIONS, COMPANION_INSTRUCTIONS
from app.companion_runtime import CompanionRuntime
from app.companion_answer_reliability import control_draft
from app.companion_contracts import CompanionDraft, CompanionAnswerDraft
from app.companion_knowledge import build_reviewed_knowledge_tool
from app.config import get_settings
from app.travel_goal_router import route_travel_goal
from app.companion_state import build_planning_brief
from evals.companion_knowledge_strategy import Reader, CountingTool
from evals.companion_provider_smoke import failure_details, public_endpoint


async def run(output, case_ids=None):
    if output.exists():
        raise RuntimeError('Refusing to overwrite evaluation evidence')
    prior = json.loads((Path(__file__).parent / 'fixtures/companion_answer_reliability_failures.json').read_text(encoding='utf-8'))
    cases = [dict(id=row['blind_id'], text=row['input'], history=row['history']) for row in prior]
    cases += [
        dict(id='conditional', text='我不喜欢排队，想在苏州慢慢走，有什么带条件的建议？'),
        dict(id='live_price', text='南京现在门票多少钱？'),
        dict(id='reservation', text='南京博物院明天还有预约名额吗？'),
        dict(id='queue_now', text='拙政园今天排队多久？'),
        dict(id='source_missing', text='南京为什么叫六朝古都？请给出文献来源。'),
        dict(id='original_rationale', text='为什么当前行程把西湖安排在18点？'),
        dict(id='planning', text='帮我规划南京三天行程'),
    ]
    solo = '一个人旅游有什么建议？'
    history = [dict(id='solo-pref', user='我想一个人去苏州慢慢逛，喜欢园林，不喜欢紧凑安排。', assistant='可以围绕园林与街巷讨论慢节奏的体验。')]
    # Registered upper bound: 8 normal travel requests; no sensitive retries.
    cases += [dict(id=f'solo_single_{i}', text=solo, filter_probe=True) for i in range(3)]
    cases += [dict(id=f'solo_multi_{i}', text=solo, history=history, filter_probe=True) for i in range(3)]
    cases += [dict(id=f'normal_probe_{i}', text='第一次独自旅行，怎样让节奏轻松一点？', filter_probe=True) for i in range(2)]
    if case_ids:
        cases = [case for case in cases if case['id'] in case_ids]
        if len(cases) != len(set(case_ids)):
            raise ValueError('Unknown or duplicate case IDs')
    settings = get_settings()
    if not settings.planner_api_key.get_secret_value() or not settings.planner_model:
        raise RuntimeError('Real provider credentials required')
    report = dict(real=True, database_used=False, model=settings.planner_model, provider=settings.planner_provider,
        endpoint=public_endpoint(settings.planner_base_url), proxy=public_endpoint(settings.planner_proxy_url),
        temperature=1.0, top_p=0.95, reasoning_effort='low', max_output_tokens=8000,
        format_repair_limit=1, sensitive_retry_limit=0, maximum_cases=len(cases)+(0 if case_ids else 4),
        prompt_sha256=hashlib.sha256((GENERAL_KNOWLEDGE_INSTRUCTIONS+COMPANION_INSTRUCTIONS).encode()).hexdigest(),
        planned_cases=cases, fact_tool='absent; unavailable-fact tests, no fabricated live provider', rows=[], complete=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    save()
    tool = await build_reviewed_knowledge_tool()
    async def one(case):
        provider = ModelCompanionProvider(capture_visible_outputs=True)
        counted = CountingTool(tool)
        history = case.get('history', [])
        goal = route_travel_goal(case['text'], history)
        started = perf_counter()
        row = dict(id=case['id'], input=case['text'], history=history, filter_probe=case.get('filter_probe',False), goal=goal.model_dump(mode='json'))
        try:
            if goal.target_runtime == 'companion':
                result = await CompanionRuntime(Reader(), provider, counted).run(session_id='reliability-real', turn_id=case['id'], message=case['text'], goal=goal, messages=history)
                row['output'] = result.model_dump(mode='json')
            else:
                row['output'] = None
                row['route_only'] = True
                brief = build_planning_brief('reliability-real',case['id'],case['text'],goal,history)
                row['planning_brief'] = brief.model_dump(mode='json') if brief else None
        except Exception as exc:
            row['failure'] = failure_details(exc)
        row.update(latency_seconds=perf_counter()-started, model_calls=len(provider.observations), model_observations=provider.observations, rag_calls=counted.calls, retrieval_seconds=counted.seconds)
        usages = [o['usage'] for o in provider.observations if o.get('usage')]
        row['total_tokens'] = sum(u.get('total_tokens',0) for u in usages) if usages else None
        for observation in reversed(provider.observations):
            if observation.get('visible_output'):
                try:
                    payload = json.loads(observation['visible_output'])
                    draft = (CompanionDraft if 'response_text' in payload else CompanionAnswerDraft).model_validate(payload)
                    gate_started = perf_counter()
                    repaired, issues = control_draft(draft,case['text'])
                    row['local_control_seconds'] = perf_counter()-gate_started
                    row['original_draft'] = draft.model_dump(mode='json')
                    row['controlled_draft'] = repaired.model_dump(mode='json')
                    row['control_issues'] = issues
                except Exception:
                    row['raw_draft_parseable'] = False
                break
        report['rows'].append(row)
        save()
        print(json.dumps({k:row.get(k) for k in ['id','model_calls','total_tokens','latency_seconds','failure','control_issues']},ensure_ascii=False),flush=True)
        return row
    for case in cases:
        await one(case)
    # Real chained dialogue: history is exactly the actually published replies.
    history=[]
    chain = [] if case_ids else ['南京有什么文化特色？','我喜欢园林和慢慢散步，不喜欢排队。有什么体验方向？','苏州和南京哪个更适合这样的节奏？','帮我规划南京三天行程，以历史文化为主。']
    for i,text in enumerate(chain):
        row=await one(dict(id=f'chain_{i+1}',text=text,history=list(history)))
        result=row.get('output')
        if result:
            history.append(dict(id=f'chain_{i+1}',user=text,assistant=result['response_text'],companion_result=result))
    report['complete']=True
    save()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cases',nargs='+')
    args=parser.parse_args()
    asyncio.run(run(args.output,args.cases))
