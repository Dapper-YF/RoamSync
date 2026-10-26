import json,socket,ssl,os,urllib.parse,asyncio,httpx,platform
from pathlib import Path
from app.config import get_settings
from app.database import session_factory,PlanningRun
from sqlalchemy import select,func
async def main():
 s=get_settings();u=urllib.parse.urlsplit(s.planner_base_url);p=urllib.parse.urlsplit(s.planner_proxy_url)
 def dns(host):
  try:return {'addresses':sorted({x[4][0] for x in socket.getaddrinfo(host,None)}),'ok':True}
  except Exception as e:return {'ok':False,'error_type':type(e).__name__}
 out={'endpoint':{'scheme':u.scheme,'host':u.hostname,'port':u.port or 443,'path':u.path},'endpoint_dns':dns(u.hostname),'explicit_proxy':{'scheme':p.scheme,'host':p.hostname,'port':p.port,'auth_present':bool(p.username)},'proxy_dns':dns(p.hostname)if p.hostname else None,'environment_proxies':{k:bool(os.environ.get(k))for k in ['HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy']},'no_proxy':os.environ.get('NO_PROXY',''),'model':s.planner_model,'provider':s.planner_provider,'request_timeout':s.planner_timeout_seconds,'client_retries':s.planner_max_retries,'worker_concurrency':s.agent_worker_concurrency,'run_timeout':s.agent_run_timeout_seconds,'research_reasoning_effort':s.research_reasoning_effort,'planner_reasoning_effort':s.planner_reasoning_effort,'output_limit':s.planner_max_output_tokens,'versions':{'python':platform.python_version(),'httpx':httpx.__version__}}
 try:
  async with httpx.AsyncClient(proxy=s.planner_proxy_url,timeout=20)as c:
   r=await c.get(s.planner_base_url.rstrip('/')+'/models');out['unauthenticated_tls_probe']={'status':r.status_code,'http_version':r.http_version,'tls_response_received':True}
 except Exception as e:out['unauthenticated_tls_probe']={'error_type':type(e).__name__,'cause_type':type(e.__cause__).__name__ if e.__cause__ else None}
 async with session_factory()as session:
  out['active_runs']=await session.scalar(select(func.count()).select_from(PlanningRun).where(PlanningRun.status.in_(['queued','researching','planning','validating'])))
 print(json.dumps(out,ensure_ascii=True))
asyncio.run(main())
