"""Real AMap + Tavily photo lookup; no database or model calls."""
import asyncio,hashlib,json,subprocess,sys
from pathlib import Path
from time import monotonic
ROOT=Path('E:/Study/RoamSync-product-closeout-stage2-20261024')
OUT=Path(__file__).parent/'photos-real-providers2.json'
if OUT.exists():raise ValueError('Refuse overwrite')
sys.path.insert(0,str(ROOT/'backend'))
from app.config import Settings
from app.place_content.provider import AMapContentProvider,stable_place_id
from app.place_content.reference_images import PlaceReferenceImages
from app.external_facts import search_tavily
configured=Settings(_env_file='E:/Study/RoamSync/.env')
settings=configured.model_copy(update={key:str(getattr(configured,key)).replace('host.docker.internal','127.0.0.1') for key in ('tavily_proxy_url','tavily_base_url')})
events=[]
async def search(settings,**kwargs):
    start=monotonic()
    result=await search_tavily(settings,**kwargs)
    events.append({'kind':'tavily','request':kwargs,'seconds':monotonic()-start,'queried_at':result.queried_at,'payload':result.payload})
    return result
report={'kind':'real provider regression, not model/independent travel evaluation','commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'results':[],'events':events}
async def run():
    service=PlaceReferenceImages(AMapContentProvider(settings.amap_rest_key),settings,search=search)
    for pid in ['B020001R2Q','B020001B0C']:
        start=monotonic();result=await service.lookup(stable_place_id(pid),pid)
        report['results'].append({'provider_id':pid,'seconds':monotonic()-start,'result':result})
        OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        print(pid,result['status'],len(result['images']),flush=True)
asyncio.run(run())

