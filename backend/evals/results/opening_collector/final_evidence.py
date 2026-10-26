import asyncio,copy,json
from pathlib import Path
from dataclasses import asdict
from evals.phase25_final import snapshot
import evals.knowledge_coverage as k
from evals.travel_facts.run import benchmark
from app.travel_facts.official_collector import PROFILES,collect
OUT=Path('/app/evals/results/opening_collector')
def save(name,value): (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
async def main():
    k.OUT=OUT/'knowledge_regression'
    await k.run('final')
    b=await benchmark();save('foundation_benchmark.json',b)
    payload=json.loads(Path('/app/tests/fixtures/opening_hours/nanjing.json').read_text())
    raw=copy.deepcopy(payload['data']['list'][0]);raw['content']=raw.pop('introduction')
    async def gateway(profile,page,cursor): return {'code':0,'count':1,'data':{'total':1,'list':[raw]}}
    result=await collect(PROFILES['nanjing_museum'],gateway=gateway)
    save('schema_change_drill.json',{'controlled':True,'change':'required introduction renamed to content','result':asdict(result),'no_truth':not result.accepted_snapshots and not result.exception_scan_complete})
    save('final_source.json',snapshot())
    print('benchmark',b['passed_cases'],b['case_count'],'drill',result.collection_status)
asyncio.run(main())
