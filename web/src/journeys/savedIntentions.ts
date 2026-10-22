import { assistantRequest } from '../product/arrangementApi';
export type SavedIntention = { id:string;source_session_id:string;source_message_id:string;source_text:string;captured_at:string;place_text:string;city_text:string|null;intended_date:string|null;time_period:string|null;status:'active'|'cancelled'|'transferred';version:number;identity_status:string;linked_arrangement_item_id:string|null };
const KEY='roamsync.intentions.known-sessions.v1';
export function rememberIntentionSession(id:string){
  try{const known=knownIntentionSessions();localStorage.setItem(KEY,JSON.stringify([...new Set([...known,id])]))}catch{/* Server save remains valid if local storage is unavailable. */}
}
export function knownIntentionSessions():string[]{
  try{const saved:unknown=JSON.parse(localStorage.getItem(KEY)||'[]');return [...new Set([...(Array.isArray(saved)?saved.filter((x):x is string=>typeof x==='string'):[]),...Object.keys(localStorage).filter(k=>k.startsWith('roamsync.assistant.session.')).map(k=>localStorage.getItem(k)!).filter(Boolean)])]}catch{return []}
}
export async function listSavedIntentions(){const ids=knownIntentionSessions();if(!ids.length)return assistantRequest<SavedIntention[]>('/saved-intentions');const all:SavedIntention[]=[];for(let i=0;i<ids.length;i+=100){const query=new URLSearchParams();for(const id of ids.slice(i,i+100))query.append('session_id',id);all.push(...await assistantRequest<SavedIntention[]>(`/saved-intentions?${query}`))}return all.sort((a,b)=>b.captured_at.localeCompare(a.captured_at))}
export function revokeIntention(i:SavedIntention){return assistantRequest<SavedIntention>(`/saved-intentions/${i.id}/revoke`,{method:'POST',body:JSON.stringify({source_session_id:i.source_session_id,expected_version:i.version})})}
export function transferIntention(i:SavedIntention,tripId:string,tripVersion:number){return assistantRequest<SavedIntention>(`/saved-intentions/${i.id}/transfer`,{method:'POST',body:JSON.stringify({source_session_id:i.source_session_id,expected_version:i.version,trip_id:tripId,expected_trip_version:tripVersion})})}
