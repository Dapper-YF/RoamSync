import type {DayPlan,PlanRevision,PlaceCandidate} from '../domain/types';
import type {Choice} from '../product/arrangementApi';
import {reviewDays} from './handbookModel';

export function JourneyReview({days,items,revision,places,protectedIds,stale,unverified,busy,onDay,onAccept,onContinue,onClose,onReject}:{
 days:DayPlan[];items:Choice[];revision:PlanRevision;places:PlaceCandidate[];protectedIds:string[];
 stale:boolean;unverified:boolean;busy:boolean;onDay:(id:string)=>void;onAccept:()=>void;onContinue:()=>void;onClose:()=>void;onReject:()=>void;
}){
 const review=reviewDays(days,items,revision,places,protectedIds);
 const changed=review.flatMap(d=>d.changes);
 const scope=review.map(d=>d.date.slice(5)).join('、');
 const outside=days.filter(d=>!review.some(r=>r.date===d.date));
 const unknown=review.some(d=>!d.day);
 return <section id="journey-review" className="journey-review" aria-label="调整预览">
  <p className="journeys-eyebrow">AI 建议 · 尚未采用</p>
  <h2>先看变化，再决定</h2>
  <p>{scope||'日期范围待核对'} · {changed.length?`${changed.length}项变化`:'没有识别到活动时间、地点或预计费用变化'}。采用前，已保存安排保持原样。</p>
  <p className="journey-review-reason">{revision.reason||'这份建议尚未提供调整理由，请继续和助手核对。'}</p>
  {review.map(d=><div className="journey-review-day" key={d.date}>
   <strong>{d.date}</strong>{d.day&&<button onClick={()=>onDay(d.day!.id)}>查看这一天</button>}
   {d.changes.length>0?<ul>{d.changes.map(r=><li key={r.id}>
    <span>{r.state==='added'?'新增':r.state==='removed'?'移除':'调整'}</span> <strong>{r.label}</strong>
    {r.before&&r.activity&&r.before.placeId!==r.activity.placeId&&<p>地点：{r.before.name} → {r.label}</p>}
    <p>{r.state==='changed'?`${r.before!.scheduledTime.slice(0,5)} · ${r.before!.durationMinutes}分钟 → ${r.time} · ${r.duration}分钟`:r.state==='removed'?`${r.time} · ${r.duration}分钟 → 不再排入`:`${r.time} · ${r.duration}分钟`}</p>
    {r.before&&r.activity&&r.activity.estimatedCostFen!=null&&r.before.estimatedCostFen!==r.activity.estimatedCostFen&&<p>预计费用 ¥{(r.before.estimatedCostFen/100).toFixed(2)} → ¥{(r.activity.estimatedCostFen/100).toFixed(2)}（参考，非报价）</p>}
    {r.before&&r.activity&&!!r.before.scheduleLocked!==!!r.activity.scheduleLocked&&<p>固定时间：{r.before.scheduleLocked?'是':'否'} → {r.activity.scheduleLocked?'是':'否'}</p>}
    {r.reason&&<p className="handbook-muted">{r.reason}</p>}
   </li>)}</ul>:<p>活动时间、地点与预计费用保持原样。</p>}
   {d.kept.length>0&&<details><summary>保留的内容 · {d.kept.length}项</summary><ul>{d.kept.map(r=><li key={r.id}>{r.time||'时间未定'} · {r.label}{r.state==='free'?'（有意留白）':r.state==='optional'?'（备选）':r.state==='undated'?'（未排程）':''}</li>)}</ul></details>}
  </div>)}
  {outside.length>0&&<p className="handbook-muted">范围外日期保持原样：{outside.map(d=>d.date.slice(5)).join('、')}。</p>}
  <p className="handbook-muted">预约、执行进度与留白仍由服务端核对。交通需要按新时间重新查询。</p>
  {stale&&<p role="alert">建议已过期，请重新商量，不能覆盖新安排。</p>}
  {unverified&&<p role="alert">暂时无法核对建议依据的安排版本，请重新读取后再采用。</p>}
  {unknown&&<p role="alert">建议包含当前旅行之外的日期，请继续商量并核对范围。</p>}
  <div className="handbook-actions">
   <button className="journeys-primary" disabled={busy||stale||unverified||unknown} onClick={onAccept}>采用{scope}的调整</button>
   <button disabled={busy} onClick={onContinue}>继续商量</button>
   <button disabled={busy} onClick={onClose}>返回原安排</button>
   <details><summary>不采用这份建议</summary><button disabled={busy} onClick={onReject}>放弃建议</button></details>
  </div>
 </section>;
}
