import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {AssistantPage,TravelAssistantProvider} from './TravelAssistant';
import type {CandidatePresentation} from '../domain/types';
const candidate:CandidatePresentation={protocol_version:2,draft_id:'d',draft_version:3,prepared_id:'p',prepared_hash:'prepared-binding',presentation_hash:'presentation-binding',stage:'ready',title:'南京一日',city:'南京',start_date:'2026-11-01',end_date:'2026-11-01',summary:'上午游湖，午间留白。',stops:[{ref:'lake',name:'玄武湖',address:'玄武巷1号',day_date:'2026-11-01',start_time:'09:00',end_time:'11:00',duration_minutes:120,note:'按你的要求停留两小时',place_ref:{place_id:'lake',external_ref:{provider:'amap',provider_place_id:'B1'}},images:[]}],windows:[],routes:[],warnings:[],blockers:[],change_summary:[],trip_id:null,operation_id:null};
const session={id:'s',trip_id:null,latest_run_id:null,messages:[],pending_action:{id:'legacy',title:'南京',summary:'只记录日期',start_date:'2026-11-01',end_date:'2026-11-01',choices:[]}};
const response=(body:unknown,status=200)=>new Response(JSON.stringify(body),{status});
const mount=()=>{
  // Saving switches to the persisted Trip and reads its arrangement. Session
  // fixtures must not masquerade as that endpoint's unrelated response type.
  const sessionFetch=globalThis.fetch;
  vi.stubGlobal('fetch',(input:RequestInfo|URL,init?:RequestInit)=>
    typeof input==='string' && input.endsWith('/arrangement-items')
      ? Promise.resolve(response({version:1,trip:{id:'trip',title:'南京一日',destination:'南京',
          start_date:'2026-11-01',end_date:'2026-11-01',version:1},days:[],items:[]}))
      : sessionFetch(input,init));
  return render(<MemoryRouter initialEntries={['/']}><TravelAssistantProvider><AssistantPage/></TravelAssistantProvider></MemoryRouter>);
};
beforeEach(()=>{sessionStorage.clear();localStorage.clear();vi.stubEnv('VITE_DISCOVERY_PRODUCT','true')});
afterEach(()=>{vi.unstubAllEnvs();vi.unstubAllGlobals()});
it('does not represent metadata as an adoptable itinerary',async()=>{vi.stubGlobal('fetch',vi.fn(async()=>response(session)));mount();expect(await screen.findByRole('button',{name:'创建旅行并生成日程'})).toBeVisible();expect(screen.queryByRole('button',{name:/采用|保存到我的安排/})).toBeNull();expect(screen.getByText(/目前只有创建信息/)).toBeVisible();});
it('sends exactly the published binding and shows saving until confirmed',async()=>{let finish!:(r:Response)=>void;const writes:Array<{url:string,body:Record<string,unknown>}>=[];vi.stubGlobal('fetch',vi.fn(async(url:string,init?:RequestInit)=>{const body=JSON.parse(String(init?.body??'{}'));writes.push({url,body});if(url.endsWith('/candidate-decision'))return new Promise<Response>(resolve=>{finish=resolve});return response({...session,pending_action:null,candidate});}));mount();fireEvent.click(await screen.findByRole('button',{name:'保存到我的安排'}));await waitFor(()=>expect(finish).toBeDefined());expect(screen.getByText('正在保存到我的安排')).toBeVisible();expect(screen.queryByText('已保存到我的安排')).toBeNull();const write=writes.find(r=>r.url.endsWith('/candidate-decision'))!;expect(write.url).toBe('/api/v1/assistant/sessions/s/candidate-decision');expect(write.body).toEqual({protocol_version:2,request_id:expect.any(String),prepared_id:'p',prepared_hash:'prepared-binding',presentation_hash:'presentation-binding',accept:true});finish(response({...session,pending_action:null,candidate:{...candidate,stage:'saved',trip_id:'trip'},trip_id:'trip'}));await screen.findByRole('link',{name:'查看我的安排'});expect(writes.some(r=>r.url.endsWith('/decision'))).toBe(false);});
it('preserves a specific conflict message and never claims a failed save succeeded',async()=>{vi.stubGlobal('fetch',vi.fn(async(url:string)=>url.endsWith('/candidate-decision')?response({detail:{code:'candidate_expired',message:'候选已过期，请重新核对地点和路线。'}},409):response({...session,pending_action:null,candidate})));mount();fireEvent.click(await screen.findByRole('button',{name:'保存到我的安排'}));expect(await screen.findByText(/候选已过期，请重新核对地点和路线/)).toBeVisible();expect(screen.queryByText('已保存到我的安排')).toBeNull();expect(screen.queryByText(/安排刚刚有了新修改/)).toBeNull();});
it('uses candidate projection once and suppresses the legacy metadata card',async()=>{vi.stubGlobal('fetch',vi.fn(async()=>response({...session,candidate})));mount();await screen.findByRole('button',{name:'保存到我的安排'});expect(screen.queryByText('只记录日期')).toBeNull();fireEvent.click(screen.getByRole('button',{name:'继续调整'}));await waitFor(()=>expect(screen.getByRole('textbox')).toHaveFocus());expect(screen.getByText(candidate.summary)).toBeVisible();});

it('reuses the same exact request identity after an uncertain network failure',async()=>{
  const requests:Array<Record<string,unknown>>=[];
  vi.stubGlobal('fetch',vi.fn(async(url:string,init?:RequestInit)=>{
    if(url.endsWith('/candidate-decision')){
      requests.push(JSON.parse(String(init?.body)));
      if(requests.length===1)throw new Error('连接中断，请重试');
      return response({...session,pending_action:null,candidate:{...candidate,stage:'saved',trip_id:'trip'},trip_id:'trip'});
    }
    return response({...session,pending_action:null,candidate});
  }));
  mount();fireEvent.click(await screen.findByRole('button',{name:'保存到我的安排'}));
  await screen.findByText(/连接中断，请重试/);
  fireEvent.click(screen.getByRole('button',{name:'保存到我的安排'}));
  await screen.findByRole('link',{name:'查看我的安排'});
  expect(requests).toHaveLength(2);
  expect(requests[1]).toEqual(requests[0]);
});

it('rereads the same session on explicit recovery and enables only its new binding',async()=>{
  let reads=0;
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>{
    if(url.endsWith('/candidate-decision'))return response({detail:{code:'candidate_expired',message:'候选已过期'}},409);
    reads++;
    return response({...session,pending_action:null,candidate:reads<3?candidate:{...candidate,prepared_id:'p-new',presentation_hash:'new'}});
  }));
  mount();fireEvent.click(await screen.findByRole('button',{name:'保存到我的安排'}));
  await screen.findByText(/保存未完成：候选已过期/);
  await waitFor(()=>expect(reads).toBe(2));
  expect(screen.queryByRole('button',{name:'保存到我的安排'})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'重新读取当前状态'}));
  expect(await screen.findByRole('button',{name:'保存到我的安排'})).toBeEnabled();
  expect(reads).toBe(3);
});
