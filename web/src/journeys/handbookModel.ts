import type { Activity, DayPlan, PlanRevision, PlaceCandidate } from '../domain/types';
import type { Choice } from '../product/arrangementApi';
export type HandbookRow = {id:string;date:string;label:string;time:string;duration?:number;state:'saved'|'added'|'changed'|'removed'|'free'|'undated'|'optional';activity?:Activity;before?:Activity;choice?:Choice;reason?:string};
export function defaultHandbookDay(days:DayPlan[],selected:string,today:string){return days.find(d=>d.id===selected)||days.find(d=>d.date===today)||days[0]}
export function handbookRows(day:DayPlan,items:Choice[],revision?:PlanRevision,places:PlaceCandidate[]=[],protectedIds:string[]=[]):HandbookRow[]{
 const target=!!revision&&(!revision.planningGoals?.targetDays.length||revision.planningGoals.targetDays.includes(day.date));
 const all=day.activities;
 const matched=new Set<string>();
 const rows:HandbookRow[]=target?revision!.activities.filter(a=>a.dayDate===day.date).map(p=>{
  // An explicit replacement is authoritative. A place visited twice is ambiguous.
  const samePlace=all.filter(a=>a.placeId===p.placeCandidateId&&!matched.has(a.id));
  const before=p.replacesActivityId?all.find(a=>a.id===p.replacesActivityId&&!matched.has(a.id)):samePlace.length===1?samePlace[0]:undefined;
  if(before)matched.add(before.id);
  const place=places.find(a=>a.id===p.placeCandidateId);
  const samePlaceIdentity=before?.placeId===p.placeCandidateId;
  const activity:Activity|undefined=before&&samePlaceIdentity?{...before,scheduledTime:p.plannedStartTime,durationMinutes:p.durationMinutes,estimatedCostFen:p.estimatedCostFen,scheduleLocked:p.locked}:place?{id:p.candidateId,placeId:place.id,name:place.name,originalName:place.name,category:place.category,neighborhood:place.neighborhood,coordinates:place.coordinates,scheduledTime:p.plannedStartTime,durationMinutes:p.durationMinutes,importance:'normal',estimatedCostFen:p.estimatedCostFen,status:'planned',scheduleLocked:p.locked,version:1,updatedAt:'',source:place.source}:undefined;
  const unchanged=before&&samePlaceIdentity&&before.scheduledTime.slice(0,5)===p.plannedStartTime.slice(0,5)&&before.durationMinutes===p.durationMinutes&&(p.estimatedCostFen==null||before.estimatedCostFen===p.estimatedCostFen)&&!!before.scheduleLocked===!!p.locked;
  return {id:p.candidateId,date:day.date,label:(samePlaceIdentity?before?.name:undefined)||p.placeName||place?.name||'地点名称待核对',time:p.plannedStartTime.slice(0,5),duration:p.durationMinutes,state:before?(unchanged?'saved':'changed'):'added',activity,before,reason:p.reason};
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

export function reviewDays(days:DayPlan[],items:Choice[],revision:PlanRevision,places:PlaceCandidate[]=[],protectedIds:string[]=[]){
 const targets=revision.planningGoals?.targetDays;
 // Without a day scope the existing contract replaces the whole itinerary.
 const dates=[...new Set([...(targets?.length?targets:days.map(d=>d.date)),...revision.activities.map(a=>a.dayDate)])].sort();
 return dates.map(date=>{
  const day=days.find(d=>d.date===date);
  const rows=handbookRows(day||{id:'',date,activities:[]} as unknown as DayPlan,items,revision,places,protectedIds);
  return {date,day,rows,changes:rows.filter(r=>['added','changed','removed'].includes(r.state)),kept:rows.filter(r=>['saved','free','undated','optional'].includes(r.state))};
 });
}

export function stopEnd(time:string,duration?:number){
 if(!/^\d{2}:\d{2}$/.test(time)||duration==null||!Number.isFinite(duration))return '';
 const [h,m]=time.split(':').map(Number);const minutes=h*60+m+duration;
 return `${minutes>=1440?'次日 ':''}${String(Math.floor(minutes/60)%24).padStart(2,'0')}:${String(minutes%60).padStart(2,'0')}`;
}
