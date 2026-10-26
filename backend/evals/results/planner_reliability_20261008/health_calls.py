import asyncio,json,time,hashlib,sys,os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel,ConfigDict,ValidationError
from app.config import get_settings
from app.model_client import build_model_client,create_model_response
from app.openai_planner import normalize_structured_json,translate_model_error
from app.destination_research import ResearchOutput,RESEARCH_INSTRUCTIONS,search_results
from app.planning_context import build_planning_context
from app.database import session_factory
import uuid
ROOT=Path('/tmp/roamsync_health');ROOT.mkdir(exist_ok=True)
class Health(BaseModel):
 model_config=ConfigDict(extra='forbid')
 status:Literal['ok']
 ok:Literal[True]
def save(name,value): (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
settings=get_settings();assert settings.planner_max_retries==0
rows=[];requestlog=[];httplog=[]
async def reqhook(req):
 body=json.loads(req.content);messages=body.get('messages',[])
 requestlog.append({'host':req.url.host,'path':req.url.path,'method':req.method,'json_body_sha256':hashlib.sha256(req.content).hexdigest(),'body_bytes':len(req.content),'message_sizes':[{'role':x['role'],'chars':len(x['content']),'utf8_bytes':len(x['content'].encode())}for x in messages],'model':body.get('model'),'response_format':body.get('response_format'),'stream':body.get('stream'),'reasoning_effort':body.get('reasoning_effort'),'thinking_enabled':body.get('thinking',{}).get('type'),'max_tokens':body.get('max_tokens')})
async def resphook(res):httplog.append({'status':res.status_code,'http_version':res.http_version,'content_type':res.headers.get('content-type'),'request_id':res.headers.get('x-request-id')})
def client():
 c=build_model_client(settings);c._client.event_hooks={'request':[reqhook],'response':[resphook]};return c
async def call(index,kind,c):
 started=time.perf_counter();row={'index':index,'kind':kind,'transport':'release configured explicit proxy','retries':0}
 try:
  if kind=='research':
   payload=json.loads(Path('/tmp/health_research_input.json').read_text(encoding='utf-8'));args={'instructions':RESEARCH_INSTRUCTIONS,'input_text':json.dumps(payload,ensure_ascii=False),'text_format':{'type':'json_schema','name':'destination_research','schema':ResearchOutput.model_json_schema()},'reasoning_effort':settings.research_reasoning_effort,'max_output_tokens':settings.planner_max_output_tokens}
  elif kind=='structured':args={'instructions':'Return a single JSON object: status is ok and ok is true. No other fields.','input_text':'JSON health check.','text_format':{'type':'json_schema','name':'provider_health','schema':Health.model_json_schema()},'reasoning_effort':'low','max_output_tokens':1000}
  else:args={'instructions':'Reply with exactly HEALTH_OK.','input_text':'Connectivity health check.','reasoning_effort':'low','max_output_tokens':1000}
  reqstart=len(requestlog);httpstart=len(httplog);response=await create_model_response(c,settings,model=settings.planner_model,**args)
  raw=response.output_text;(ROOT/f'call{index}_terminal.txt').write_text(raw,encoding='utf-8');row.update(status=response.status,finish_reason=response.finish_reason,output_chars=len(raw),output_sha256=hashlib.sha256(raw.encode()).hexdigest(),usage=response.usage.model_dump()if hasattr(response.usage,'model_dump')else None)
  if response.status!='completed':row.update(success=False,error_category='model_incomplete_output')
  elif kind=='simple':row.update(success=raw.strip()=='HEALTH_OK',error_category=None if raw.strip()=='HEALTH_OK'else'model_invalid_output')
  else:
   normalized=normalize_structured_json(raw)
   try:
    parsed=(ResearchOutput if kind=='research'else Health).model_validate_json(normalized);row.update(success=True,parse_valid=True,error_category=None,normalization_applied=normalized!=raw)
    if kind=='research':row['research_places']=len(parsed.places);row['schema_sha256']=hashlib.sha256(json.dumps(ResearchOutput.model_json_schema(),sort_keys=True).encode()).hexdigest()
   except ValidationError as e:
    row.update(success=False,parse_valid=False,error_category='model_invalid_json_or_schema',validation_errors=e.errors(include_input=False,include_url=False))
    try:json.loads(normalized)
    except json.JSONDecodeError as je:row['json_failure']={'position':je.pos,'line':je.lineno,'column':je.colno,'message':je.msg,'normalized_chars':len(normalized),'remaining_chars':len(normalized)-je.pos}
  row['request_observations']=requestlog[reqstart:];row['http_observations']=httplog[httpstart:]
 except Exception as e:
  chain=[];x=e
  while x and len(chain)<5:chain.append(type(x).__name__);x=x.__cause__
  translated=translate_model_error(e);status=getattr(e,'status_code',None);category='http_protocol_error'if'RemoteProtocolError'in chain else'network_or_tls_connection_failure'if any(n in chain for n in ['ConnectError','APIConnectionError'])else'timeout'if any('Timeout'in n for n in chain)else'gateway_or_provider_http_error'if status and status>=500 else'provider_http_rejection'if status else'provider_or_client_exception'
  row.update(success=False,error_category=category,exception_chain=chain,http_status=status,translated_code=translated.code,retryable=translated.retryable,request_observations=requestlog[reqstart:],http_observations=httplog[httpstart:])
 row['latency_seconds']=round(time.perf_counter()-started,3);rows.append(row);save(f'call{index}.json',row);save('summary.json',rows);print(json.dumps({k:row.get(k)for k in ['index','kind','success','status','finish_reason','error_category','latency_seconds','exception_chain','translated_code']},ensure_ascii=True),flush=True)
async def main():
 role=sys.argv[1]
 if role=='api_simple' or role=='api_structured':
  c=client()
  try:await call(1 if role=='api_simple'else 6,'simple'if role=='api_simple'else'structured',c)
  finally:await c.close()
 else:
  c=client()
  try:await call(2,'simple',c)
  finally:await c.close()
  c=client()
  try:await call(3,'research',c);await call(4,'research',c)
  finally:await c.close()
  c=client()
  try:await call(5,'structured',c)
  finally:await c.close()
asyncio.run(main())
