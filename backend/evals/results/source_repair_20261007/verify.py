import asyncio,json,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
from evals.phase25_final import snapshot
from evals.travel_facts.run import benchmark
P=Path('evals/results/source_repair_20261007')
def save(n,v):(P/n).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
b=json.loads((P/'baseline_source.json').read_text());f=snapshot();live=json.loads((P/'live/live_acceptance.json').read_text())
assert f==live['snapshot']
changed=[n for n,h in b['files'].items() if f['files'].get(n)!=h];added=sorted(set(f['files'])-set(b['files']))
assert not changed and len(added)==3
save('final_source.json',f);bench=asyncio.run(benchmark());save('foundation_benchmark.json',bench)
xml=ET.parse(P/'linux_focused.xml').getroot().find('testsuite').attrib
save('verification.json',{'baseline':b['sha256'],'final':f['sha256'],'changed_existing':changed,'added':added,'linux_focused':{k:xml[k] for k in ('tests','errors','failures','skipped')},'foundation':[bench['passed_cases'],bench['case_count']],'runtime_path_changed':False,'regular_exception_readiness':'NOT READY','source_repair_result':'PARTIAL','next_slice':'End-to-End Demo Acceptance'})
with zipfile.ZipFile(P/'slice_source_overlay.zip','x',zipfile.ZIP_DEFLATED) as z:
 for n in added:z.write(n,n)
 z.write(P/'baseline_source.json','baseline_source.json');z.write(P/'final_source.json','final_source.json')
print(json.dumps(json.loads((P/'verification.json').read_text()),ensure_ascii=False))
