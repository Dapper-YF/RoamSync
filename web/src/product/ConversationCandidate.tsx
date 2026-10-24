import {useState} from 'react';
import {Link} from 'react-router-dom';
import type {CandidatePresentation} from '../domain/types';
import {approvedPhotos} from '../data/placeContentRepository';
import {PlaceCover} from '../components/PlacePhotos';
import {clock} from './arrangementApi';
import './ConversationCandidate.css';

const stageLabels: Record<CandidatePresentation['stage'], string> = {
  ready:'未保存的安排',needs_input:'还需要补充信息',saving:'正在保存到我的安排',saved:'已保存到我的安排',needs_review:'需要重新核对',stale:'候选已过期',failed:'候选准备失败',
};
export function ConversationCandidate({candidate:c,busy,saving=false,invalidated=false,onSave,onContinue}: {candidate:CandidatePresentation;busy:boolean;saving?:boolean;invalidated?:boolean;onSave:()=>void;onContinue:()=>void}) {
  const [details,setDetails]=useState(false);
  const stage=saving?"saving":invalidated&&c.stage==='ready'?"needs_review":c.stage;
  const money=(fen:number)=>`¥${Number((fen/100).toFixed(2))}`;
  const modes:Record<string,string>={walk:'步行',driving:'驾车',transit:'公交'};
  const names=new Map(c.stops.map(s=>[s.ref,s.name]));
  const rows=[...c.stops.map(s=>({...s,label:s.name,kind:'visit'})),...c.windows].sort((a,b)=>a.day_date.localeCompare(b.day_date)||(a.start_time??'').localeCompare(b.start_time??''));
  return <section className="conversation-candidate" aria-label="对话中的行程候选">
    <p className="conversation-candidate-stage" role="status">{stageLabels[stage]}</p>
    <h2>{c.title}</h2><p className="conversation-candidate-dates">{c.city} · {c.start_date}—{c.end_date}</p>
    <p>{c.summary}</p>
    {c.change_summary.length>0&&<div className="conversation-candidate-changes" aria-label="这次调整">{c.change_summary.map((text,i)=><p key={i}>{text}</p>)}</div>}
    <div className="conversation-candidate-stops">{c.stops.map(stop=>{
      const photos=stop.place_ref ? approvedPhotos(stop.images,stop.place_ref.place_id,stop.place_ref.external_ref.provider_place_id) : [];
      return <article key={stop.ref}><PlaceCover photos={photos} full/><h3>{stop.name}</h3><p>{stop.address}</p><p>{stop.day_date} · {clock(stop.start_time)}—{clock(stop.end_time)} · 停留{stop.duration_minutes}分钟</p>{stop.note&&<p>{stop.note}</p>}</article>;
    })}</div>
    {c.routes.map((r,i)=><p className="conversation-candidate-route" key={`${r.from_ref}-${r.to_ref}-${i}`}>{names.get(r.from_ref)} → {names.get(r.to_ref)} · {modes[r.mode]??r.mode}约{r.duration_minutes}分钟 · {r.distance_meters}米 · {r.provider}路线估计</p>)}
    {c.windows.map(w=><p key={w.ref}>{w.label} · {w.day_date}{w.start_time?` ${clock(w.start_time)}—${clock(w.end_time)}`:''}</p>)}
    {c.warnings.map((text,i)=><p className="conversation-candidate-warning" key={i}>{text}</p>)}
    {c.blockers.map((text,i)=><p role="alert" key={i}>{text}</p>)}
    {stage==='stale'&&<p>这份候选已不能保存，请继续调整以重新核对地点和路线。</p>}
    {stage==='failed'&&<p>这次未能准备好候选，请继续补充要求或重试。</p>}
    <div className="conversation-candidate-actions">
      {stage==='ready'&&<button className="conversation-candidate-save" disabled={busy||c.blockers.length>0} onClick={onSave}>保存到我的安排</button>}
      {stage!=='saved'&&<button disabled={busy||stage==='saving'} onClick={onContinue}>继续调整</button>}
      <button aria-expanded={details} onClick={()=>setDetails(v=>!v)}>{details?'收起完整候选':'查看完整候选'}</button>
      {stage==='saved'&&c.trip_id&&<Link to={`/trips/${c.trip_id}`}>查看我的安排</Link>}
    </div>
    {details&&<div className="conversation-candidate-details"><p>只读预览 · {stage==='saved'?'已保存':'尚未保存'}</p><ol aria-label="完整候选时间轴">{rows.map(row=><li key={row.ref}><time>{row.day_date}{row.start_time?` ${clock(row.start_time)}—${clock(row.end_time)}`:''}</time><strong>{row.label}</strong>{row.kind!=='visit'&&<span>保留窗口</span>}</li>)}</ol>
      {(c.constraints||c.constraint_checks?.length||c.stops.some(s=>s.estimated_cost_fen!=null))&&<section aria-label="候选条件与费用">
        <h3>条件与费用</h3>
        {c.constraints&&<>
          <p>每日可用时间 {clock(c.constraints.daily_start_time)}—{clock(c.constraints.daily_end_time)}</p>
          <p>交通方式 {modes[c.constraints.transport_mode]??c.constraints.transport_mode}</p>
          {c.constraints.total_budget_fen!=null&&<p>总预算 {money(c.constraints.total_budget_fen)}</p>}
          {c.constraints.daily_budget_fen!=null&&<p>每日预算 {money(c.constraints.daily_budget_fen)}</p>}
          {c.constraints.max_walking_minutes!=null&&<p>步行上限 {c.constraints.max_walking_minutes}分钟 · {({inter_activity:'仅活动间交通',inter_activity_travel_only:'仅活动间交通',all_day:'全天步行',continuous:'连续步行'} as Record<string,string>)[c.constraints.walking_scope]??c.constraints.walking_scope}</p>}
        </>}
        {c.stops.filter(s=>s.estimated_cost_fen!=null).map(s=><p key={s.ref}>{s.name} · {money(s.estimated_cost_fen!)} · {s.cost_nature==='provider_reference'?'地图参考价':'规划估计'}</p>)}
        {c.stops.some(s=>s.estimated_cost_fen!=null)&&<p>费用不是真实报价，实际门票、餐饮和现场支出仍需核对。</p>}
        {c.constraint_checks?.map((check,i)=><p key={i}>{check.source_quote||check.requirement_ref} · {({satisfied:'已满足',violated:'未满足',unverified:'尚未核实'} as const)[check.status]}</p>)}
      </section>}
    </div>}
  </section>;
}
