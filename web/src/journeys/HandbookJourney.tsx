import {useCallback,useEffect,useState,useRef,type ReactNode,type FormEvent} from 'react';
import {Link,useLocation} from 'react-router-dom';
import type {Activity,DayPlan,Trip,PlanningRun,PlanRevision,PlaceCandidate,ExecutionProgress,TripExecutionAction} from '../domain/types';
import {MapCanvas} from '../components/MapCanvas';
import {EffectiveRequirements} from './EffectiveRequirements';
import {useOptionalTravelAssistant} from '../product/TravelAssistant';
import {assistantRequest,type Choice} from '../product/arrangementApi';
import {defaultHandbookDay,handbookRows,validMapRows,reviewDays,type HandbookRow} from './handbookModel';
import {localDate,tripPhase,type JourneyPageProps} from './journeyApi';
import {useJourneyScene} from './continuity';
import './handbook.css';
import {HandbookPhoto} from './HandbookPhotos';
import {ApiTripPlanningRepository} from '../data/apiTripPlanningRepository';
import {JourneyReview} from './JourneyReview';
import {stopEnd} from './handbookModel';
import './JourneyReview.css';
const handbookMapPadding:[number,number,number,number]=[44,44,44,44];

type Props=JourneyPageProps&{trip:Trip;days:DayPlan[];places:PlaceCandidate[];runs:PlanningRun[];revisions:PlanRevision[];selection:string;selectDay:(id:string)=>void;busy:boolean;error:string;notice:string;refresh:()=>Promise<void>;perform:(fn:()=>Promise<unknown>,success:string)=>Promise<void>;execution:ReactNode;route:(a:Activity,p?:Activity)=>void;progress:ExecutionProgress|null;executionAction:(a:TripExecutionAction,id?:string)=>void};
export function HandbookJourney({trip,days,places,runs,revisions,selection,selectDay,busy,error,notice,refresh,perform,execution,onAskAssistant,route,progress,executionAction}:Props){
 const assistant=useOptionalTravelAssistant();
 const location=useLocation();
 const [view,setView]=useJourneyScene<'day'|'overview'|'map'>(`trip.${trip.id}.handbook-view`,'day');
 const [preview,setPreview]=useJourneyScene<string>(`trip.${trip.id}.preview`,'');
 const seenCandidates=useRef(new Set<string>());
 const [selectedMap,setSelectedMap]=useState<string|null>(null);
 const [editing,setEditing]=useState<Activity>();
 const [items,setItems]=useState<Choice[]>([]);
 const [itemError,setItemError]=useState('');
 const [clarification,setClarification]=useJourneyScene<string>(`trip.${trip.id}.clarification`,'');
 const [extension,setExtension]=useState(30);
 const historical=tripPhase(trip,localDate())==='history';
 const day=defaultHandbookDay(days,selection,localDate());
 const pending=revisions.find(r=>r.id===preview);
 const protectedIds=[...(progress?.execution.activities.filter(a=>['arrived','in_progress','completed','skipped'].includes(a.status)).map(a=>a.activityId)||[]),...(progress?.execution.currentActivityId?[progress.execution.currentActivityId]:[])];
 const rows=day?handbookRows(day,items,pending,places,protectedIds):[];
 const mapRows=validMapRows(rows);
 const activeMap=mapRows.find(r=>r.activity?.id===selectedMap);
 const selectMap=useCallback((id:string)=>setSelectedMap(id),[]);
 const apiItems=async()=>{try{const data=await assistantRequest<{items:Choice[]}>(`/trips/${trip.id}/arrangement-items`);setItems(data.items);setItemError('')}catch{setItemError('未排程事项暂时无法读取，已保存活动仍可查看。')}};
 useEffect(()=>{void apiItems()},[trip.id,trip.version,assistant?.arrangement?.version]);
 useEffect(()=>{if(preview&&!revisions.some(r=>r.id===preview))setPreview('')},[preview,revisions]);
 useEffect(()=>{const fresh=revisions.find(r=>!seenCandidates.current.has(r.id));for(const r of revisions)seenCandidates.current.add(r.id);if(fresh){setPreview(fresh.id);const affected=reviewDays(days,items,fresh,places,protectedIds).find(d=>d.changes.length&&d.day);if(affected?.day)selectDay(affected.day.id)}},[revisions.map(r=>r.id).join(',')]);
 useEffect(()=>{const requested=(location.state as {reviewRevisionId?:string}|null)?.reviewRevisionId;if(requested&&revisions.some(r=>r.id===requested)){setPreview(requested);requestAnimationFrame(()=>document.getElementById('journey-review')?.scrollIntoView({block:'start'}))}},[location.key,revisions.map(r=>r.id).join(',')]);
 const ask=(activity?:Activity)=>{if(!day)return;onAskAssistant?.({tripId:trip.id,tripTitle:trip.title,city:trip.destination,selectedDayId:day.id,selectedDayDate:day.date,selectedActivityId:activity?.id,selectedActivityName:activity?.name})};
 const candidateDates=pending?.planningGoals?.targetDays.length?pending.planningGoals.targetDays:[...new Set(pending?.activities.map(a=>a.dayDate)||[])];
 const pendingBase=pending?runs.find(r=>r.id===pending.planningRunId)?.baseTripVersion:undefined;
 const stale=!!pending&&pendingBase!=null&&pendingBase!==trip.version;
 const unverified=!!pending&&(pendingBase==null||trip.version==null);
 const continueCandidate=()=>{if(!pending)return;const bound=days.find(d=>d.date===candidateDates[0]);onAskAssistant?.({tripId:trip.id,tripTitle:trip.title,city:trip.destination,selectedDayId:bound?.id,selectedDayDate:bound?.date})};
 async function decide(r:PlanRevision,accept:boolean){await perform(()=>assistantRequest(`/plan-revisions/${r.id}/${accept?'accept':'reject'}`,{method:'POST'}),accept?'已采用调整并重新读取安排。':'已放弃建议。');void apiItems()}
 async function edit(e:FormEvent<HTMLFormElement>){e.preventDefault();if(!editing)return;const f=new FormData(e.currentTarget);await perform(async()=>{await assistantRequest(`/activities/${editing.id}`,{method:'PUT',headers:{'X-Trip-Version':String(trip.version)},body:JSON.stringify({version:editing.version,scheduled_time:f.get('time'),duration_minutes:Number(f.get('duration'))})});setEditing(undefined)},'已保存时间修改。');void apiItems()}
 const stateNames={saved:'已保存',added:'新增 · 尚未采用',changed:'调整 · 尚未采用',removed:'移除 · 尚未采用',free:'有意留白',undated:'时间未定',optional:'备选 · 可以不去'};
 function executionActions(a:Activity){
  const p=progress;if(historical||!p||p.execution.status!=='in_progress'||p.execution.currentActivityId!==a.id||p.execution.currentDayPlanId!==day?.id)return null;
  const status=p.execution.activities.find(e=>e.activityId===a.id)?.status;
  const exp=p.currentActivityExperience;
  return <div className="handbook-actions" aria-label={`${a.name}的实际进度`}>{status==='pending'&&<><button disabled={busy} onClick={()=>executionAction('arrive',a.id)}>我已到达</button><button disabled={busy||a.canSkip===false} onClick={()=>executionAction('skip',a.id)}>跳过这站</button></>}{status==='arrived'&&<button disabled={busy} onClick={()=>executionAction('start_activity',a.id)}>开始体验</button>}{status==='in_progress'&&<><button disabled={busy} onClick={()=>executionAction('complete',a.id)}>完成这站</button>{exp?.activityId===a.id&&exp.activityExecutionId&&<><label>延长停留<select aria-label="延长停留分钟" disabled={busy} value={extension} onChange={e=>setExtension(Number(e.target.value))}>{[15,30,60,120,240,480].map(n=><option key={n} value={n}>{n}分钟</option>)}</select></label><button disabled={busy} onClick={()=>void perform(()=>new ApiTripPlanningRepository().extendStay(exp.activityExecutionId!,extension,crypto.randomUUID()),'已记录实际停留变化。')}>确认延长停留</button><button disabled={busy} onClick={()=>void perform(()=>new ApiTripPlanningRepository().leaveEarly(exp.activityExecutionId!,crypto.randomUUID()),'已记录提前离开。')}>提前离开</button></>}</>}</div>;
 }
 const renderRows=(data:HandbookRow[])=>{
  const untimed=data.filter(r=>r.state==='undated'||r.state==='optional');
  const scheduled=data.filter(r=>r.state!=='undated'&&r.state!=='optional');
  return <><ol className="handbook-timeline">{scheduled.map((r,index)=>{
   const sourceDay=days.find(d=>d.date===r.date);
   const next=scheduled.slice(index+1).find(row=>row.date===r.date&&row.activity);
   const leg=!pending&&r.activity&&next?.activity?sourceDay?.routeLegs?.find(l=>l.fromActivityId===r.activity!.id&&l.toActivityId===next.activity!.id):undefined;
   const previous=scheduled.slice(0,index).reverse().find(row=>row.date===r.date&&row.activity)?.activity;
   return <li className={`handbook-stop ${r.state}`} key={r.id}>
    <time>{r.time||'时间未定'}{r.state==='free'&&r.choice?.end?`—${r.choice.end.slice(0,5)}`:''}</time>
    <div>{(pending||r.state==='free')&&<span className="handbook-status">{r.state==='saved'?'保持原样':stateNames[r.state]}</span>}
     <h3>{r.label}</h3>
     {r.duration!=null&&<p>{r.time}—{stopEnd(r.time,r.duration)} · 停留{r.duration}分钟{r.activity?.scheduleLocked?' · 固定时间':''}</p>}
     {r.state==='changed'&&r.before&&<p>原来 {r.before.scheduledTime.slice(0,5)} · {r.before.durationMinutes}分钟</p>}
     {r.activity&&<HandbookPhoto city={trip.destination} name={r.activity.originalName || r.activity.name} coordinates={r.activity.coordinates}/>}
     {r.state==='free'&&<p>保留这段空闲，不自动补项目。</p>}
     {r.reason&&<p className="handbook-muted">{r.reason}</p>}{r.activity?.note&&<p className="handbook-muted">{r.activity.note}</p>}
     {!pending&&r.activity&&<><div className="handbook-actions"><button onClick={()=>ask(r.activity)}>和 AI 商量</button><button onClick={()=>route(r.activity!,previous)}>查询路线</button>{!historical&&<details><summary>更多操作</summary><button disabled={busy} onClick={()=>setEditing(r.activity)}>直接修改时间</button></details>}</div>{executionActions(r.activity)}</>}
     {!pending&&r.activity&&next?.activity&&<p className="handbook-connection">前往 {next.label} · {leg?`${leg.mode==='walk'?'步行':leg.mode==='driving'?'驾车':'公交'} ${leg.durationMinutes}分钟 · ${leg.isEstimated?'估算，待核实':leg.provider||'来源待核对'}`:'交通尚未查询'}</p>}
    </div>
   </li>;
  })}</ol>{untimed.length>0&&<section className="handbook-unscheduled" aria-label="当天未排程事项"><h3>这天想去，时间未定</h3><p>先留在这里，不自动填入时间轴。</p><ul>{untimed.map(r=><li key={r.id}><strong>{r.label}</strong><p>{r.state==='optional'?'备选，可以不去':'已记下，尚未排程'}{r.time?` · ${r.time}`:''}</p>{!pending&&!historical&&<button onClick={()=>onAskAssistant?.({tripId:trip.id,tripTitle:trip.title,city:trip.destination,selectedDayId:sourceDayFor(r.date)?.id,selectedDayDate:r.date,prompt:`请为${r.label}建议在${r.date}的合适时间，保留已有预约和留白，先给候选。`})}>请 AI 建议时间</button>}</li>)}</ul></section>}</>;
 };
 function sourceDayFor(date:string){return days.find(d=>d.date===date)}
 return <main className="journeys-page handbook"><Link to="/trips" className="journeys-back">← 我的安排</Link><header className="handbook-heading"><p className="journeys-eyebrow">MY JOURNEY</p><h1>{trip.title}</h1><p>{trip.destination} · {trip.startDate}—{trip.endDate}</p></header><HandbookPhoto city={trip.destination}/>{error&&<p role="alert">{error}<button onClick={()=>void refresh()}>重新读取</button></p>}{notice&&<p role="status">{notice}</p>}{itemError&&<p role="alert">{itemError}<button onClick={()=>void apiItems()}>重试读取事项</button></p>}
 <div className="handbook-section-heading"><div><h2>{pending?'建议中的日程':'已保存日程'}</h2><p className="handbook-muted">{historical?'过去或已归档的安排，可在此回看。':'调整先给建议，采用后才保存。'}</p></div><button onClick={()=>setView(view==='map'?'day':'map')}>{view==='map'?'返回时间轴':'查看当天地图 ↗'}</button></div><div className="handbook-days" role="tablist" aria-label="旅行日期">{days.map((d,i)=><button role="tab" aria-selected={day?.id===d.id} key={d.id} onClick={()=>{selectDay(d.id);setSelectedMap(null)}}>第{i+1}天<small>{d.date.slice(5)}</small></button>)}</div><nav className="handbook-views" aria-label="旅行观看方式">{(['day','overview','map'] as const).map((v,i)=><button key={v} aria-pressed={view===v} onClick={()=>setView(v)}>{['当天日程','整趟概览','地图'][i]}</button>)}</nav>
 {day&&!pending&&<div className="handbook-day-summary"><p><strong>{day.date}</strong> · {day.activities.length}个已安排地点{items.some(i=>i.day_date===day.date&&!i.activity_id&&['selected','optional'].includes(i.kind))?' · 有时间未定的事项':''}</p>{!historical&&<button className="journeys-primary" disabled={busy} onClick={()=>ask()}>和 AI 调整这一天</button>}</div>}
 {pending&&<JourneyReview days={days} items={items} revision={pending} places={places} protectedIds={protectedIds} stale={stale} unverified={unverified} busy={busy} onDay={id=>{selectDay(id);setView('day')}} onAccept={()=>void decide(pending,true)} onContinue={continueCandidate} onClose={()=>setPreview('')} onReject={()=>void decide(pending,false)}/>}
 {revisions.length>0&&!pending&&<div className="handbook-pending">{revisions.map(r=><button key={r.id} onClick={()=>setPreview(r.id)}>查看待采用的调整 · {r.planningGoals?.targetDays.join('、')||'核对日期'}</button>)}</div>}
 {pending&&<p className="handbook-preview-label" role="status">正在对照 AI 建议 · 标记的改动尚未保存</p>}
 {view==='overview'?<div className="handbook-overview">{days.map((d,i)=><article key={d.id}><h2>第{i+1}天 · {d.date}</h2><p>{d.theme||d.label}</p>{renderRows(handbookRows(d,items,pending,places,protectedIds))}{!handbookRows(d,items,pending,places,protectedIds).length&&<p>尚未安排</p>}<button onClick={()=>{selectDay(d.id);setView('day')}}>查看这一天</button></article>)}</div>:<><h2>{day?.date} · {day?.theme||day?.label||'按自己的节奏'}</h2>{view==='map'?<><div className="handbook-map"><MapCanvas fitPadding={handbookMapPadding} activities={mapRows.map(r=>r.activity!)} routeLegs={pending?[]:(day?.routeLegs||[]).filter(l=>!l.isEstimated&&l.path&&l.path.length>1)} selectedActivityId={selectedMap} onSelectActivity={selectMap}/></div><p className="handbook-muted">{pending?'调整预览':'已保存安排'} · 仅显示已知地点；坐标缺失的事项仍在日程中。路线未经核实则不绘制。</p>{activeMap&&<p>{activeMap.label} · {activeMap.time}</p>}{mapRows.length===0&&<p>这天还没有已核实坐标，可继续查看日程。</p>}</>:<>{rows.length?renderRows(rows):<p className="handbook-empty">这一天尚未安排，可以先保留空闲。</p>}</>}</>}
 {!pending&&(tripPhase(trip,localDate())==='active'||['in_progress','paused','completed'].includes(progress?.execution.status||''))&&execution}
 {runs.filter(r=>['queued','researching','planning','validating'].includes(r.status)).map(r=><p role="status" key={r.id}>正在准备调整，已保存日程保持原样。</p>)}
 {runs.filter(r=>r.status==='awaiting_clarification').map(r=><section key={r.id}><h3>还需要补充一点</h3>{r.pendingInterrupt?.questions?.map(q=><p key={q}>{q}</p>)}<label>补充要求<textarea value={clarification} onChange={e=>setClarification(e.target.value)}/></label><button disabled={busy||!clarification.trim()} onClick={()=>void perform(()=>new ApiTripPlanningRepository().answerPlanningRun(r.id,clarification),'补充已提交。')}>提交补充</button></section>)}
 {runs[0]?.status==='failed'&&<p role="alert">最近一次调整未完成；已有日程与仍可用的候选会保留。{runs[0].errorMessage}</p>}
 {editing&&<form className="handbook-editor" onSubmit={edit}><h3>直接修改 · {editing.name}</h3><label>开始时间<input type="time" name="time" defaultValue={editing.scheduledTime.slice(0,5)} required/></label><label>停留分钟<input type="number" name="duration" min={5} max={1440} step={1} defaultValue={editing.durationMinutes} required/></label><div className="handbook-actions"><button disabled={busy}>保存时间修改</button><button type="button" onClick={()=>setEditing(undefined)}>暂不修改</button></div></form>}
 {items.some(i=>!i.day_date&&!i.activity_id&&i.kind!=='cancelled')&&<section className="handbook-undated"><h2>还没定哪天</h2>{items.filter(i=>!i.day_date&&!i.activity_id&&i.kind!=='cancelled').map(i=><p key={i.id}>{i.label} · {i.time_period||''} · {i.kind==='optional'?'备选':'日期与时间未定'} <button onClick={()=>onAskAssistant?.({tripId:trip.id,tripTitle:trip.title,city:trip.destination,prompt:`请把${i.label}安排到这趟旅行中合适的一天，保留已有预约和留白，先生成候选，等我采用后保存。`})}>请 AI 建议放哪天</button></p>)}</section>}<details className="handbook-context"><summary>旅行要求与出发前核对</summary><EffectiveRequirements kind="trip" id={trip.id} version={trip.version} disabled={busy||historical} onChanged={()=>void refresh()}/><p>住宿：{trip.accommodation||'尚未记录'}。营业时间、门票和预约需出发前核实。</p></details>
 <footer className="handbook-adjust"><div><strong>✧ 让 AI 帮你改这一天</strong><p>{historical?'这是过去或已归档的安排。':pending?'正在商量这份候选，采用后才会保存。':day?`${day.date} · 比如“下午轻松一点”“帮我找一家附近的餐厅”`:'可以先和助手聊聊'}</p></div><button className="handbook-compose-trigger" disabled={!day||busy||historical} onClick={()=>ask()} aria-label="打开当天调整助手"><span>告诉 AI，你想怎么调整…</span><span aria-hidden="true">↑</span></button></footer></main>;
}
