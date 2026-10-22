import type { Activity, DayPlan, PlanRevision, PlaceCandidate } from '../domain/types';
import type { Choice } from '../product/arrangementApi';
export type HandbookRow = {id:string;date:string;label:string;time:string;duration?:number;state:'saved'|'added'|'changed'|'removed'|'free'|'undated'|'optional';activity?:Activity;before?:Activity;choice?:Choice;reason?:string};
export function defaultHandbookDay(days:DayPlan[],selected:string,today:string){return days.find(d=>d.id===selected)||days.find(d=>d.date===today)||days[0]}
export function handbookRows(day:DayPlan,items:Choice[],revision?:PlanRevision,places:PlaceCandidate[]=[],protectedIds:string[]=[]):HandbookRow[]{
 const target=!!revision&&(!revision.planningGoals?.targetDays.length||revision.planningGoals.targetDays.includes(day.date));
 const all=day.activities;
 const rows:HandbookRow[]=target?revision!.activities.filter(a=>a.dayDate===day.date).map(p=>{
  const before=all.find(a=>a.id===p.replacesActivityId)||all.find(a=>a.placeId===p.placeCandidateId);
  const place=places.find(a=>a.id===p.placeCandidateId);
  const activity:Activity|undefined=before?{...before,scheduledTime:p.plannedStartTime,durationMinutes:p.durationMinutes}:place?{id:p.candidateId,placeId:place.id,name:place.name,originalName:place.name,category:place.category,neighborhood:place.neighborhood,coordinates:place.coordinates,scheduledTime:p.plannedStartTime,durationMinutes:p.durationMinutes,importance:'normal',estimatedCostFen:p.estimatedCostFen,status:'planned',scheduleLocked:p.locked,version:1,updatedAt:'',source:place.source}:undefined;
  return {id:p.candidateId,date:day.date,label:p.placeName||before?.name||place?.name||'地点名称待核对',time:p.plannedStartTime.slice(0,5),duration:p.durationMinutes,state:before?(before.scheduledTime.slice(0,5)===p.plannedStartTime.slice(0,5)&&before.durationMinutes===p.durationMinutes?'saved':'changed'):'added',activity,before,reason:p.reason};
 }):all.map(a=>({id:a.id,date:day.date,label:a.name,time:a.scheduledTime.slice(0,5),duration:a.durationMinutes,state:'saved',activity:a}));
 if(target)for(const a of all)if(!rows.some(r=>r.before?.id===a.id)){
  const preserved=a.scheduleLocked||['active','completed','skipped'].includes(a.status)||protectedIds.includes(a.id);
  rows.push({id:preserved?a.id:`removed-${a.id}`,date:day.date,label:a.name,time:a.scheduledTime.slice(0,5),duration:a.durationMinutes,state:preserved?'saved':'removed',before:a,activity:preserved?a:undefined});
 }
 for(const i of items.filter(i=>i.day_date===day.date&&!i.activity_id&&i.kind!=='cancelled'))rows.push({id:i.id,date:day.date,label:i.label,time:i.start?.slice(0,5)||i.time_period||'',state:i.kind==='free_window'?'free':i.kind==='optional'?'optional':'undated',choice:i});
 return rows.sort((a,b)=>(a.time||'99:99').localeCompare(b.time||'99:99'));
}
export function validMapRows(rows:HandbookRow[]){return rows.filter(r=>r.state!=='removed'&&r.activity&&r.activity.coordinates.length===2&&r.activity.coordinates.every(Number.isFinite)&&Math.abs(r.activity.coordinates[0])<=180&&Math.abs(r.activity.coordinates[1])<=90&&r.activity.coordinates.some(v=>v!==0))}
export function handbookEnabled(){try{return new URLSearchParams(location.search).get('experience')!=='legacy'&&localStorage.getItem('roamsync.handbook.enabled')!=='false'}catch{return true}}
