"""Full visible model and redacted AMap capture around the existing public harness.

No provider retry, app behavior change, fixture rescue or production writes.
The underlying runner creates an exclusive synthetic database and refuses reuse.
"""
import json
import runpy
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

source=Path(sys.argv[sys.argv.index('--app-root')+1])
output=Path(sys.argv[sys.argv.index('--output')+1]).with_suffix('.trace.ndjson')
if output.exists():
    raise SystemExit('Refusing to overwrite wire capture')
sys.path.insert(0,str(source/'backend'))

def record(value):
    value['at']=datetime.now(UTC).isoformat()
    with output.open('a',encoding='utf-8') as f:
        f.write(json.dumps(value,ensure_ascii=False,default=str)+'\n')

from app import model_client
original_model=model_client.create_model_response
async def observe_model(*args,**kwargs):
    started=monotonic()
    request={k:v for k,v in kwargs.items() if k!='on_content'}
    try:
        result=await original_model(*args,**kwargs)
        usage=getattr(result,'usage',None)
        record({'kind':'model','request':request,'seconds':round(monotonic()-started,3),
            'status':result.status,'visible_output':result.output_text,
            'usage':usage.model_dump() if hasattr(usage,'model_dump') else usage})
        return result
    except Exception as exc:
        record({'kind':'model','request':request,'seconds':round(monotonic()-started,3),
            'error_type':type(exc).__name__})
        raise
model_client.create_model_response=observe_model

from app import map_transport
original_map=map_transport.get_json
def observe_map(url,**kwargs):
    started=monotonic()
    parsed=urlsplit(url)
    safe=urlunsplit((parsed.scheme,parsed.netloc,parsed.path,
        urlencode([(k,v) for k,v in parse_qsl(parsed.query) if k.lower() not in {'key','sig','token'}]),''))
    try:
        result=original_map(url,**kwargs)
        record({'kind':'amap','url':safe,'seconds':round(monotonic()-started,3),'result':result})
        return result
    except Exception as exc:
        record({'kind':'amap','url':safe,'seconds':round(monotonic()-started,3),'error_type':type(exc).__name__})
        raise
map_transport.get_json=observe_map
runpy.run_path('E:/Study/RoamSync-stage4-evidence-20261025/run_live_v4.py',run_name='__main__')
