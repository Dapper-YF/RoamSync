"""Read-only real transport diagnosis; no secret values in output."""
import asyncio, hashlib, json, os, sys
from pathlib import Path
sys.path.insert(0,'E:/Study/RoamSync-product-closeout-stage2-20261024/backend')
from app.config import Settings
from dotenv import dotenv_values
from app.external_facts import search_tavily
settings=Settings(_env_file='E:/Study/RoamSync/.env')
values=dotenv_values('E:/Study/RoamSync/.env')
candidate=(values.get('HTTPS_PROXY') or values.get('HTTP_PROXY') or '').replace('host.docker.internal','127.0.0.1')
configured=settings.tavily_proxy_url.replace('host.docker.internal','127.0.0.1')
def error_chain(exc):
    chain=[]
    while exc is not None:
        chain.append(type(exc).__name__);exc=exc.__cause__ or exc.__context__
    return chain
async def run():
    results=[]
    for label,proxy in [('configured',configured),('existing_local_proxy',candidate)]:
        if label=='existing_local_proxy' and (not proxy or proxy==configured):continue
        try:
            result=await search_tavily(settings.model_copy(update={'tavily_proxy_url':proxy,'search_timeout_seconds':16}),query='苏州 拙政园 图片',max_results=2,include_images=True,retry_attempts=1)
            results.append({'mode':label,'proxy_present':bool(proxy),'status':'available','sources':len(result.payload.get('results',[])),
                'images':len(result.payload.get('images',[])),'payload':result.payload})
        except Exception as exc:
            results.append({'mode':label,'proxy_present':bool(proxy),'status':'failed','error_chain':error_chain(exc)})
    out=Path(__file__).with_name('image-transport-probe.json')
    if out.exists():raise ValueError('Refuse overwrite')
    out.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([{k:v for k,v in r.items() if k!='payload'} for r in results]))
asyncio.run(run())
