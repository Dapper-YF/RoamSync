import {fireEvent, render, screen, within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {expect, it, vi} from 'vitest';
import {ConversationCandidate} from './ConversationCandidate';
import type {CandidatePresentation} from '../domain/types';
export const candidate: CandidatePresentation = {protocol_version:2,draft_id:'draft',draft_version:1,prepared_id:'prepared',prepared_hash:'core',presentation_hash:'display',stage:'ready',title:'成都慢游',city:'成都',start_date:'2026-11-01',end_date:'2026-11-01',summary:'先去公园，再逛街巷，午间留给午餐。',stops:[{ref:'park',name:'人民公园',address:'祠堂街9号',day_date:'2026-11-01',start_time:'09:00',end_time:'11:00',duration_minutes:120,note:'停留时间按你的要求安排。',place_ref:{place_id:'canonical-park',external_ref:{provider:'amap',provider_place_id:'park-provider'}},images:[]},{ref:'alley',name:'宽窄巷子',address:'长顺上街',day_date:'2026-11-01',start_time:'13:00',end_time:'14:30',duration_minutes:90,note:'',place_ref:{place_id:'canonical-alley',external_ref:{provider:'amap',provider_place_id:'alley-provider'}},images:[]}],windows:[{ref:'lunch',kind:'meal',label:'午餐留白',day_date:'2026-11-01',start_time:'11:30',end_time:'12:30'}],routes:[{from_ref:'park',to_ref:'alley',day_date:'2026-11-01',mode:'walk',distance_meters:1200,duration_minutes:18,provider:'amap'}],warnings:['开放情况尚未核实'],blockers:[],change_summary:[],trip_id:null,operation_id:null};
function mount(value = candidate, onSave = vi.fn()) {render(<MemoryRouter><ConversationCandidate candidate={value} busy={false} onSave={onSave} onContinue={vi.fn()}/></MemoryRouter>);return onSave;}
it('presents server order, source narrative and route without opening the full timeline',()=>{const save=mount();expect(screen.getByText(candidate.summary)).toBeVisible();expect(screen.getAllByRole('heading',{level:3}).map(n=>n.textContent)).toEqual(['人民公园','宽窄巷子']);expect(screen.getByText('祠堂街9号')).toBeVisible();expect(screen.getByText(/步行.*18分钟.*1200米.*amap/)).toBeVisible();expect(screen.queryByRole('list',{name:'完整候选时间轴'})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'查看完整候选'}));expect(within(screen.getByRole('list',{name:'完整候选时间轴'})).getByText('午餐留白')).toBeVisible();expect(screen.queryByRole('link')).toBeNull();fireEvent.click(screen.getByRole('button',{name:'保存到我的安排'}));expect(save).toHaveBeenCalledOnce();});
it.each([['saving','正在保存到我的安排'],['stale','候选已过期'],['failed','候选准备失败'],['needs_input','还需要补充信息'],['needs_review','需要重新核对']])('does not offer adoption during %s',(stage,label)=>{mount({...candidate,stage:stage as CandidatePresentation['stage']});expect(screen.getByText(label)).toBeVisible();expect(screen.queryByRole('button',{name:'保存到我的安排'})).toBeNull();expect(screen.queryByText('已保存到我的安排')).toBeNull();});
it('shows saved navigation only for server confirmed saved candidate',()=>{mount({...candidate,stage:'saved',trip_id:'trip'});expect(screen.getByRole('link',{name:'查看我的安排'})).toHaveAttribute('href','/trips/trip');});
it('preserves the same image element when only a stop time changes',()=>{const image={url:'/api/v1/media/place-images/park.jpg',thumbnail_url:'/api/v1/media/place-images/park-small.jpg',attribution:'Author',source_url:'https://commons.wikimedia.org/wiki/File:Park.jpg',usage_basis:'reviewed_commons_license',provider:'wikimedia_commons',place_ref:candidate.stops[0].place_ref,title:'公园实景',license_name:'CC0',license_url:'https://creativecommons.org/publicdomain/zero/1.0/',changes:'裁剪'};const value={...candidate,stops:[{...candidate.stops[0],images:[image]}]};const props={busy:false,onSave:vi.fn(),onContinue:vi.fn()};const view=render(<MemoryRouter><ConversationCandidate candidate={value} {...props}/></MemoryRouter>);const photo=screen.getByRole('img');view.rerender(<MemoryRouter><ConversationCandidate candidate={{...value,draft_version:2,change_summary:['人民公园延长30分钟'],stops:[{...value.stops[0],end_time:'11:30',duration_minutes:150}]}} {...props}/></MemoryRouter>);expect(screen.getByRole('img')).toBe(photo);expect(screen.getByText('人民公园延长30分钟')).toBeVisible();});

it('renders unresolved places without photos or an adoption action',()=>{
  mount({...candidate,stage:'needs_input',stops:[{...candidate.stops[0],place_ref:null}],blockers:['请确认人民公园的具体位置']});
  expect(screen.getByRole('heading',{name:'人民公园'})).toBeVisible();
  expect(screen.getByText('请确认人民公园的具体位置')).toBeVisible();
  expect(screen.queryByRole('img')).toBeNull();
  expect(screen.queryByRole('button',{name:'保存到我的安排'})).toBeNull();
});

it('allows the server saved result to supersede a local invalidated binding',()=>{
  render(<MemoryRouter><ConversationCandidate candidate={{...candidate,stage:'saved',trip_id:'saved-trip'}} busy={false} invalidated onSave={vi.fn()} onContinue={vi.fn()}/></MemoryRouter>);
  expect(screen.getByText('已保存到我的安排')).toBeVisible();
  expect(screen.getByRole('link',{name:'查看我的安排'})).toHaveAttribute('href','/trips/saved-trip');
});

it('discloses server cost and structured constraints in the read-only details',()=>{
  mount({...candidate,constraints:{start_date:'2026-11-01',daily_start_time:'09:00',daily_end_time:'17:30',transport_mode:'walk',max_walking_minutes:null,walking_scope:'inter_activity_travel_only',total_budget_fen:30000,daily_budget_fen:20000},constraint_checks:[{requirement_ref:'budget',status:'unverified',source_quote:'控制预算',source_ref:'user:1'}],stops:[{...candidate.stops[0],estimated_cost_fen:5000,cost_nature:'planning_estimate'}]});
  expect(screen.queryByRole('region',{name:'候选条件与费用'})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'查看完整候选'}));
  const detail=screen.getByRole('region',{name:'候选条件与费用'});
  expect(detail).toHaveTextContent('每日可用时间 09:00—17:30');
  expect(detail).toHaveTextContent('总预算 ¥300');
  expect(detail).toHaveTextContent('每日预算 ¥200');
  expect(detail).toHaveTextContent('人民公园 · ¥50 · 规划估计');
  expect(detail).toHaveTextContent('费用不是真实报价');
  expect(detail).toHaveTextContent('控制预算 · 尚未核实');
  expect(detail).not.toHaveTextContent('步行上限');
});

it('does not turn unspecified server budgets or walking limits into zero-valued constraints',()=>{
  mount({...candidate,constraints:{start_date:'2026-11-01',daily_start_time:'09:00',daily_end_time:'17:30',transport_mode:'walk',max_walking_minutes:null,walking_scope:'inter_activity',total_budget_fen:null,daily_budget_fen:null}});
  fireEvent.click(screen.getByRole('button',{name:'查看完整候选'}));
  const detail=screen.getByRole('region',{name:'候选条件与费用'});
  expect(detail).not.toHaveTextContent('总预算');
  expect(detail).not.toHaveTextContent('每日预算');
  expect(detail).not.toHaveTextContent('步行上限');
});
