"""Export recorded user-visible outputs only; no calls, rescoring or resampling."""
import json,subprocess,sys
from pathlib import Path
from xml.etree import ElementTree
root=Path(__file__).parent
source=Path('E:/Study/RoamSync-product-closeout-stage2-20261024')
def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
sections=['# Recorded development model outputs\n\nThese are public development/regression runs, not independent scores. All failed attempts are retained. Visible model wire output and tool/state details are in the adjacent JSON/NDJSON files.\n']
for path in sorted(root.glob('*real*.json')):
    try: data=read(path)
    except (ValueError,UnicodeError): continue
    if not isinstance(data,dict) or not data.get('records'): continue
    sections.append('\n## '+path.name+'\n')
    for record in data['records']:
        raw=record.get('raw') or {}
        sections.append('\n### Turn '+str(record.get('turn',''))+'\n\nUser:\n\n'+str(record.get('user',''))+'\n\nAssistant:\n\n'+str(raw.get('assistant',''))+'\n')
(root/'DEVELOPMENT_FULL_OUTPUTS.md').write_text(''.join(sections),encoding='utf-8')
tests=[]
for path in sorted(root.rglob('*.xml')):
    try:
        xml=ElementTree.parse(path).getroot()
        suites=[xml] if xml.tag=='testsuite' else list(xml.findall('testsuite'))
        tests.append({'path':path.relative_to(root).as_posix(),
            'tests':sum(int(item.get('tests',0)) for item in suites),
            'failures':sum(int(item.get('failures',0)) for item in suites),
            'errors':sum(int(item.get('errors',0)) for item in suites),
            'skipped':sum(int(item.get('skipped',0)) for item in suites)})
    except (ValueError,ElementTree.ParseError): pass
(root/'test-results-index.json').write_text(json.dumps(tests,indent=2)+'\n',encoding='utf-8')
commits=[]
for commit in subprocess.check_output(['git','rev-list','--reverse','ed3797e..736e3b7'],cwd=source,text=True).splitlines():
    commits.append({'commit':commit,'subject':subprocess.check_output(['git','show','-s','--format=%s',commit],cwd=source,text=True).strip(),
        'files':subprocess.check_output(['git','diff-tree','--no-commit-id','--name-only','-r',commit],cwd=source,text=True).splitlines()})
(root/'batch-commits.json').write_text(json.dumps(commits,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'development_outputs':len(sections),'xml_reports':len(tests),'product_commits':len(commits)}))
