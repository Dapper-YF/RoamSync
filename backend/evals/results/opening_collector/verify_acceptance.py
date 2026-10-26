import json,xml.etree.ElementTree as ET
from pathlib import Path
from evals.phase25_final import snapshot
P=Path('/app/evals/results/opening_collector')
def load(n):return json.loads((P/n).read_text(encoding='utf-8-sig'))
def save(n,v):(P/n).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
a=load('starting_source.json');b=snapshot();f=load('final_source.json');r=load('rediscovery.json')
changed=[n for n,h in a['files'].items() if b['files'].get(n)!=h];added=sorted(set(b['files'])-set(a['files']))
assert not changed and len(added)==3 and b==f==r['snapshot']
assert load('formal_before.json')==load('formal_after.json')
test={}
for n in ('focused','backend_final'):
 root=ET.parse(P/(n+'.xml')).getroot();suite=root.find('testsuite');test[n]={k:suite.attrib[k] for k in ('tests','failures','errors','skipped')}
new=load('knowledge_regression/final_results.json')['summary'];old=json.loads(Path('/app/evals/results/opening_hours_v1/knowledge_regression/final_results.json').read_text())['summary']
assert new==old
save('acceptance_summary.json',{'offline_source_sha256':b['sha256'],'production_source_sha256':a['sha256'],'old_source_files_unchanged':not changed,'added_source_files':added,'tests':test,'foundation_passed':load('foundation_benchmark.json')['passed_cases'],'companion_passed':load('companion_regression/real_companion.json')['passed'],'formal_state_unchanged':True,'knowledge_summary_unchanged':True,'knowledge_summary':new,'status':'PARTIAL','regular_exception_readiness':'NOT READY'})
print(json.dumps(load('acceptance_summary.json'),ensure_ascii=False))
