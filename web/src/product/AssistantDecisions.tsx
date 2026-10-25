import { ConversationCandidate } from "./ConversationCandidate";
import { Link } from "react-router-dom";
import { useTravelAssistant } from "./TravelAssistant";
import { choiceLabels, clock } from "./arrangementApi";
import {RevisionReview} from './RevisionReview';

export function AssistantDecisions() {
  const a = useTravelAssistant();
  const preview = a.session?.pending_action;
  const activities = a.arrangement?.days.flatMap(d => d.activities) ?? [];
  const changes = a.revision?.proposed_snapshot.activities.filter(item => {
    const old = activities.find(activity => activity.id === item.replaces_activity_id || activity.place_id === item.place_candidate_id);
    const date = a.arrangement?.days.find(day => day.activities.some(activity => activity.id === old?.id))?.date;
    return !old || old.place_id !== item.place_candidate_id || clock(old.scheduled_time) !== clock(item.planned_start_time) || old.duration_minutes !== item.duration_minutes || date !== item.day_date;
  }) ?? [];
  const hasWalkingLimit = a.revision?.planning_goals?.hard_goals?.max_walking_minutes != null || a.revision?.goal_satisfaction?.results.some(r => r.evidence.walking_scope === "inter_activity_travel_only");
  const stale = a.run?.base_trip_version != null && a.arrangement != null && a.run.base_trip_version !== a.arrangement.version;
  return <>
    {a.session?.candidate && <ConversationCandidate candidate={a.session.candidate} busy={a.busy} saving={a.candidateSaving} invalidated={a.candidateInvalidated} onSave={()=>void a.saveCandidate()} onContinue={a.continueDiscussion}/>}
    {preview && !a.session?.candidate && <section className="travel-assistant-decision" aria-label="待确认的创建信息"><h2>{preview.tool==='reschedule_trip'?'确认旅行日期修改':'确认创建信息'}</h2>
      <p>{preview.tool==='reschedule_trip'?'确认后修改旅行日期，具体日程仍需重新核对。':'目前只有创建信息，尚未生成可核对的日程；确认后将创建旅行并请求生成日程。'}</p>
      <p>{preview.start_date} — {preview.end_date}</p><p>{preview.summary}</p>
      <ul>{preview.choices?.map((i, n) => <li key={n}><strong>{i.label}</strong> · {choiceLabels[i.kind]}{i.kind === "blank_day" && i.day_date && ` · ${i.day_date}`}{i.start && ` · ${i.day_date} ${clock(i.start)}—${clock(i.end)}`}</li>)}</ul>
      <button disabled={a.busy} onClick={() => void a.decidePreview(true)}>{preview.tool==='reschedule_trip'?'确认修改旅行日期':'创建旅行并生成日程'}</button>
      <button disabled={a.busy} onClick={() => a.continueDiscussion()}>继续讨论</button>
      <button disabled={a.busy} onClick={() => void a.decidePreview(false)}>放弃这份建议</button>
    </section>}
    {a.run && ["queued", "researching", "planning", "validating"].includes(a.run.status) && <p role="status">正在核对需要协调的安排，当前安排保持不变…</p>}
    {a.run?.status === "failed" && <p role="alert">这次没能形成可采用的调整。{a.run.error_message} 原安排保持不变。</p>}
    {a.run?.status === "awaiting_clarification" && <p>{a.run.pending_interrupt?.questions?.join(" ")}</p>}
    {a.revision?.status === "pending" && <section className="travel-assistant-decision" aria-label="局部调整建议"><h2>核对这次调整</h2><p>{a.revision.review?'以下差异来自候选快照，采用后才保存。':a.revision.reason}</p>
      {a.arrangement&&<Link to={`/trips/${a.arrangement.trip.id}`} state={{reviewRevisionId:a.revision.id}} onClick={a.closeAssistant}>回到日程，查看完整改动与保留内容 →</Link>}
      {a.revision.review?<RevisionReview review={a.revision.review}/>:<ul>{changes.slice(0, 3).map(i => {
        const old = activities.find(o => o.id === i.replaces_activity_id || o.place_id === i.place_candidate_id);
        return <li key={i.candidate_id}>{old && old.place_id === i.place_candidate_id ? old.display_name : "新地点（请核对方案说明）"} · {i.day_date}<br />
          {old && `原来 ${clock(old.scheduled_time)} / ${old.duration_minutes}分钟 → `}{clock(i.planned_start_time)} / {i.duration_minutes}分钟{i.reason && <p>{i.reason}</p>}</li>;
      })}</ul>}
      {!changes.length && <p>请回到日程核对这次调整的完整内容。</p>}
      {hasWalkingLimit && <p>目前只核对活动间的交通步行；景区内部和公交换乘步行尚未完整核实，不能据此保证整日总步行量。</p>}
      <p>采用后才会保存；固定活动、留白及其他要求仍会检查。</p>
      {stale && <p role="alert">安排已有新修改，这份候选已过期。请保留当前安排，重新提出调整要求。</p>}
      <button disabled={a.busy || stale || !a.revision.presentation_hash || !a.revision.review?.complete} onClick={() => void a.decideRevision(true)}>采用这次调整</button><button disabled={a.busy} onClick={() => void a.decideRevision(false)}>保留原安排</button>
    </section>}
    {a.arrangement && <p className="travel-assistant-saved"><Link to={`/trips/${a.arrangement.trip.id}`}>查看{a.arrangement.trip.title}的已保存安排 →</Link></p>}
  </>;
}
