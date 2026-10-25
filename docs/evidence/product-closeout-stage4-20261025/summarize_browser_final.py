"""State comparisons for the one continuous Suzhou browser run."""
import json
from pathlib import Path
root=Path(__file__).parent/'runtime-final-v6/browser-states'
out=Path(__file__).parent/'browser-final-state-comparisons.json'
def read(name): return json.loads((root/(name+'.json')).read_text(encoding='utf-8'))
formal=('trips','day_plans','activities','trip_preferences','route_legs','trip_arrangement_items')
before=read('before-generation');preview=read('preview75-unsaved');adopted=read('adopted75')
pending=read('pending60');restored=read('pending60-after-refresh')
result={'product_commit':pending['git_commit'],'app_sha256':pending['app_sha256'],
    'source_same_all':len({item['app_sha256'] for item in [before,preview,adopted,pending,restored]})==1,
    'no_formal_rows_before_explicit_adopt':all(not snapshot['tables'][table]
        for snapshot in [before,preview] for table in formal),
    'formal_saved_after_explicit_adopt':len(adopted['tables']['trips'])==1,
    'pending_modification_formal_unchanged':all(adopted['tables'][table]==pending['tables'][table] for table in formal),
    'refresh_formal_unchanged':all(pending['tables'][table]==restored['tables'][table] for table in formal),
    'refresh_exact_revisions_preserved':pending['tables']['plan_revisions']==restored['tables']['plan_revisions'],
    'pending_revisions':[{'id':row['id'],'status':row['status']} for row in pending['tables']['plan_revisions']],
    'scope':'Actual state checks; do not imply independent-score or complete factual-query success'}
if (root/'adopted60-after-refresh.json').exists():
    final=read('adopted60-after-refresh')
    previous={row['id']:row for row in adopted['tables']['activities']}
    result['final_source_same']=final['app_sha256']==pending['app_sha256']
    result['activity_deltas']=[{'id':row['id'],'changes':{key:{'before':previous[row['id']].get(key),'after':value}
        for key,value in row.items() if previous[row['id']].get(key)!=value}}
        for row in final['tables']['activities'] if row!=previous[row['id']]]
    result['preserved_tables']={table:adopted['tables'][table]==final['tables'][table]
        for table in ('day_plans','trip_preferences','trip_arrangement_items','place_candidates','source_records')}
    result['trip_versions']=[snapshot['tables']['trips'][0]['version'] for snapshot in [adopted,pending,final]]
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({key:value for key,value in result.items() if isinstance(value,bool)}))
