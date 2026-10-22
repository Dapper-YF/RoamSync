import { HandbookJourney } from "./HandbookJourney";
import { handbookEnabled,defaultHandbookDay } from "./handbookModel";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, Clock3, Navigation, Sparkles } from "lucide-react";
import { ApiTripPlanningRepository } from "../data/apiTripPlanningRepository";
import type { Activity, DayPlan, PlaceCandidate, ExecutionProgress, PlanRevision, PlanningRun, Trip, TripExecutionAction } from "../domain/types";
import { errorMessage, localDate, tripPhase, type JourneyPageProps } from "./journeyApi";
import { useJourneyScene } from "./continuity";
import { EffectiveRequirements } from "./EffectiveRequirements";
import "./journeys.css";
import { ArrangementExtras } from "../product/ArrangementExtras";
import { useOptionalTravelAssistant } from "../product/TravelAssistant";

const api = new ApiTripPlanningRepository();
const inFlight = (r: PlanningRun) => ["queued", "researching", "planning", "validating"].includes(r.status);
const executionLabels = { pending: "待前往", arrived: "已到达", in_progress: "正在体验", completed: "已完成", skipped: "已跳过" };
export function JourneyPage(props: JourneyPageProps) { const { tripId = "" } = useParams(); return <Journey key={tripId} id={tripId} {...props} />; }
function Journey({ id, onAskAssistant, onRoute }: JourneyPageProps & { id: string }) {
  const assistant = useOptionalTravelAssistant();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [days, setDays] = useState<DayPlan[]>([]);
  const [progress, setProgress] = useState<ExecutionProgress | null>(null);
  const [progressError, setProgressError] = useState("");
  const [runs, setRuns] = useState<PlanningRun[]>([]);
  const [revisions, setRevisions] = useState<PlanRevision[]>([]);
  const [places, setPlaces] = useState<PlaceCandidate[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [selection, setSelection] = useJourneyScene(`trip.${id}.scene`, { day: "", request: "", scope: "all", activity: "", clarification: "" });
  const [busy, setBusy] = useState(false);
  const [extension, setExtension] = useJourneyScene(`trip.${id}.extension`, 30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const phase = trip ? tripPhase(trip, localDate()) : "upcoming";
  const historical = phase === "history";
  async function load() {
    const results = await Promise.allSettled([api.getTrip(id), api.getDays(id), api.listPlanningRuns(id), api.getExecutionProgress(id), api.getCandidates(id)]);
    if (results[0].status === "fulfilled") setTrip(results[0].value); else setError(errorMessage(results[0].reason));
    if (results[1].status === "fulfilled") setDays(results[1].value); else setError(errorMessage(results[1].reason));
    if (results[2].status === "fulfilled") {
      setRuns(results[2].value);
      const pending = results[2].value.filter(r => r.status === "awaiting_confirmation");
      const fetched = await Promise.allSettled(pending.map(r => api.getPlanRevision(r.id)));
      setRevisions(fetched.flatMap(r => r.status === "fulfilled" && r.value.status === "pending" ? [r.value] : []));
      if (fetched.some(r => r.status === "rejected")) setError("有待确认的调整暂时无法读取，请刷新后核对。日程尚未改变。");
    } else setError("暂时无法读取方案调整，请刷新重试。");
    if (results[3].status === "fulfilled") { setProgress(results[3].value); setProgressError(""); } else setProgressError("暂时无法读取实际旅行进度，请重试。已确认日程仍可查看。");
    if (results[4].status === "fulfilled") { setPlaces(results[4].value); setNames(Object.fromEntries(results[4].value.map(p => [p.id, p.name]))); }
    setLoading(false);
  }
  useEffect(() => { void load(); }, [id, assistant?.arrangement?.version, assistant?.session?.latest_run_id, assistant?.run?.status, assistant?.revision?.id]);
  useEffect(() => { if (!runs.some(inFlight) && !["in_progress", "paused"].includes(progress?.execution.status || "")) return; const timer = setInterval(() => void load(), 4000); return () => clearInterval(timer); }, [id, runs.some(inFlight), progress?.execution.status]);
  const shownDay = defaultHandbookDay(days, selection.day, localDate());
  const allActivities = days.flatMap(d => d.activities);
  const adjustmentDay = days.find(d => d.id === selection.scope) || shownDay;
  const selectedActivity = adjustmentDay?.activities.find(a => a.id === selection.activity);
  const current = allActivities.find(a => a.id === progress?.execution.currentActivityId);
  const orderedExecution = progress?.execution.activities.filter(a => a.dayPlanId === progress.execution.currentDayPlanId) || [];
  const currentPosition = orderedExecution.findIndex(a => a.activityId === progress?.execution.currentActivityId);
  const nextExecution = orderedExecution.slice(currentPosition + 1).find(a => ["pending", "arrived"].includes(a.status));
  const next = allActivities.find(a => a.id === nextExecution?.activityId);
  async function perform(operation: () => Promise<unknown>, success: string) {
    setBusy(true); setError(""); setNotice("");
    try { await operation(); setNotice(success); await assistant?.refreshArrangement(); await load(); } catch (e) { setError(errorMessage(e)); await load(); } finally { setBusy(false); }
  }
  async function propose() {
    if (!selection.request.trim()) return;
    await perform(() => api.createPlanningRun(id, selection.request, { runType: allActivities.length ? "replan" : "initial_plan", selectedDayId: selectedActivity ? adjustmentDay?.id : selection.scope === "all" ? undefined : selection.scope, selectedActivityId: selectedActivity?.id }), "正在准备候选方案。已确认日程保持原样，核对后由你决定是否采用。");
  }
  function action(action: TripExecutionAction, activityId?: string) {
    const executionId = progress?.execution.id;
    if (executionId) void perform(() => api.applyTripExecutionAction(executionId, action, activityId), "实际进度已更新。");
  }
  function route(activity: Activity, previous?: Activity) {
    onRoute?.({ city: trip?.destination || "", to: { longitude: activity.coordinates[0], latitude: activity.coordinates[1], coordinate_system: "gcj02" }, from: previous ? { longitude: previous.coordinates[0], latitude: previous.coordinates[1], coordinate_system: "gcj02" } : undefined, returnTo: `/trips/${id}`, toName: activity.name, fromName: previous?.name, tripId: id, activityId: activity.id, fromActivityId: previous?.id });
  }
  const recovery = progress?.recoveryPlanning;
  const recoveryRevision = recovery?.pendingRevision || progress?.recoveryRevision;
  const latestRun = [...runs].sort((a, b) => Date.parse(b.createdAt || "") - Date.parse(a.createdAt || ""))[0];
  const terminalFailure = latestRun?.status === "failed" ? latestRun : undefined;
  if (!trip) return <main className="journeys-page"><Link to="/trips">← 旅程</Link>{error ? <p role="alert">{error}<button onClick={() => void load()}>重新读取</button></p> : <p role="status">{loading ? "正在读取旅行…" : "旅行暂不可用"}</p>}</main>;
  const executionContent = <>    {!historical && <section className="journeys-card journeys-today" aria-label="当前旅行进度"><h2>{progress?.execution.status === "completed" ? "本次旅行已结束" : progress?.execution.status === "not_started" ? (shownDay?.activities.length ? "这一天的旅行进度" : "这一天尚未安排活动") : progress?.execution.status === "paused" ? "旅行暂时停下来了" : "此刻和下一站"}</h2>{progressError ? <p role="alert">{progressError}<button onClick={() => void load()}>重试</button></p> : progress ? <>
    {progress.execution.status === "not_started" ? <><p>这里记录你主动确认的到达和完成进度。路线查询与外部地图不代表实时 GPS 导航。</p>{shownDay && <button className="journeys-primary" disabled={busy || !shownDay.activities.length} onClick={() => void perform(() => api.startTripExecution(id, shownDay.id), "已开始记录这一天的旅行进度。")}>开始{shownDay.date}的旅行</button>}</> : <><div className="journeys-current-next"><article><span className="journeys-eyebrow">现在</span><h3>{progress.currentActivityName || current?.name || "当前没有进行中的活动"}</h3>{progress.currentActivityExperience?.elapsedExperienceMinutes != null && <p>已体验{progress.currentActivityExperience.elapsedExperienceMinutes}分钟</p>}{progress.currentActivityExperience?.projectedEndAt && <p>预计结束 {new Date(progress.currentActivityExperience.projectedEndAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</p>}</article><ArrowRight size={22} /><article><span className="journeys-eyebrow">下一站</span><h3>{progress.navigationTargetName || next?.name || "今天没有下一站"}</h3>{next && <p>{next.scheduledTime.slice(0, 5)} · {next.durationMinutes}分钟</p>}{next && onRoute && <button className="journeys-secondary" onClick={() => route(next, current)}><Navigation size={16} />查询下一站路线</button>}</article></div><p>尚有{progress.execution.remainingActivityCount}项活动 · {progress.execution.scheduleDelayMinutes > 0 ? `比安排晚${progress.execution.scheduleDelayMinutes}分钟` : "暂无已记录延迟"}</p><div className="journeys-actions">{progress.execution.status === "paused" ? <button disabled={busy} onClick={() => action("resume")}>继续旅行</button> : progress.execution.status === "in_progress" && <button disabled={busy} onClick={() => action("pause")}>暂停旅行</button>}{progress.execution.status !== "completed" && progress.execution.remainingActivityCount === 0 && <button className="journeys-primary" disabled={busy} onClick={() => action("finish")}>结束本次旅行</button>}</div></>}
    </> : <p>正在读取实际进度…</p>}</section>}
    {!historical && progress?.experienceImpact && ["absorbed", "at_risk", "infeasible"].includes(progress.experienceImpact.impactState) && <section className={`journeys-card journeys-stay-impact ${progress.experienceImpact.impactState === "absorbed" ? "journeys-stay-absorbed" : "journeys-impact"}`} aria-label="实际停留对后续安排的影响"><h2>{progress.experienceImpact.impactState === "absorbed" ? "可用缓冲仍能容纳这次停留变化" : progress.experienceImpact.impactState === "at_risk" ? "停留变化压缩了后续时间" : "按当前停留时间，后续安排难以完成"}</h2><p>{progress.experienceImpact.impactState === "absorbed" ? "后续活动仍可使用已有缓冲，已确认日程没有自动改动。" : progress.experienceImpact.impactState === "at_risk" ? "后续活动时间较紧，请关注下一站及必要的调整选择。" : "需要核对后续活动和调整建议。采用新的安排仍由你明确确认。"}</p>{progress.experienceImpact.timeShiftMinutes != null && <p>实际停留带来的时间变化：{progress.experienceImpact.timeShiftMinutes}分钟</p>}{progress.experienceImpact.minimumDownstreamSlackMinutes != null && <p>后续最少可用缓冲：{progress.experienceImpact.minimumDownstreamSlackMinutes}分钟</p>}</section>}
    {!historical && (progress?.activeDisruption || recovery || progress?.riskLevel === "eta_delayed") && <section className="journeys-card journeys-impact" aria-label="旅行影响与调整"><h2>接下来的安排可能受影响</h2><p>{recovery?.reasonSummary || (progress?.activeDisruption?.eventType === "missed_time_window" ? "当前到达时间可能错过原定时间窗口。" : progress?.activeDisruption ? "当前条件下，后续日程可能无法按原安排完成。" : "预计到达时间晚于原安排。")}</p>{progress?.minimumDownstreamSlackMinutes != null && <p>后续最少可用缓冲：{progress.minimumDownstreamSlackMinutes}分钟</p>}{recovery?.status === "failed" || progress?.activeRecoveryRun?.status === "failed" ? <p>调整建议暂未生成，已确认日程保持原样。可和 AI 讨论或重新提交具体调整要求。</p> : ["queued", "planning"].includes(recovery?.status || progress?.activeRecoveryRun?.status || "") ? <p role="status">正在检查可以怎样调整。日程不会自动改动。</p> : null}{recoveryRevision && <><h3>建议的变化</h3><p>{recoveryRevision.proposedSnapshot.explanation}</p>{recoveryRevision.changeSummary.adjustedActivities.map(change => <p key={change.activityId}>{change.name || allActivities.find(a => a.id === change.activityId)?.name || "活动"}：{change.beforeStartTime.slice(0, 5)} → {change.afterStartTime.slice(0, 5)}{change.beforeDurationMinutes !== change.afterDurationMinutes && `，停留${change.beforeDurationMinutes} → ${change.afterDurationMinutes}分钟`}</p>)}<div className="journeys-actions"><button className="journeys-primary" disabled={busy} onClick={() => void perform(() => api.acceptPlanRevision(recoveryRevision.id), "已采用调整后的日程。")}>确认采用调整</button><button disabled={busy} onClick={() => void perform(() => api.rejectPlanRevision(recoveryRevision.id), "保留原日程，未采用此次调整。")}>保留原日程</button></div></>}{onAskAssistant && <button onClick={() => onAskAssistant({ tripId: id, city: trip.destination, prompt: "解释当前旅行受到的实际影响，以及可以怎样选择。" })}>请 AI 解释影响</button>}</section>}
</>;
  if (handbookEnabled()) return <HandbookJourney trip={trip} days={days} places={places} runs={runs} revisions={revisions} selection={selection.day} selectDay={day=>setSelection({...selection,day})} busy={busy} error={error} notice={notice} refresh={load} perform={perform} execution={executionContent} progress={progress} executionAction={action} onAskAssistant={onAskAssistant} onRoute={onRoute} route={route}/>;
  return <main className="journeys-page journeys-formal"><Link className="journeys-back" to="/trips">← 旅程</Link><div className="journeys-heading"><div><span className="journeys-eyebrow">{historical ? "MEMORIES TO KEEP" : phase === "active" ? "MAKE TODAY YOURS" : "LOOKING FORWARD"}</span><h1>{trip.title}</h1><p>{trip.destination} · {trip.startDate} — {trip.endDate} · {historical ? "历史安排" : phase === "active" ? "旅行中的安排" : "即将出发"}</p></div><button className="journeys-secondary" disabled={!onAskAssistant} onClick={() => onAskAssistant?.({ tripId: id, city: trip.destination, prompt: historical ? "帮我回顾这次旅行的安排。" : "结合当前日程和实际进度，下一步有什么建议？" })}><Sparkles size={17} />和 AI 聊聊</button></div>
    {error && <div className="journeys-notice" role="alert">{error}<button onClick={() => { setError(""); void load(); }}>读取最新状态</button></div>}{notice && <p className="journeys-success" role="status">{notice}</p>}
    <EffectiveRequirements kind="trip" id={trip.id} version={trip.version} disabled={busy || historical} onChanged={() => { void load(); void assistant?.refreshArrangement(); }} />
    {assistant?.arrangement?.trip.id === id && <ArrangementExtras />}
    {executionContent}
    <section className="journeys-schedule" aria-label="已确认日程"><div className="journeys-section-heading"><div><h2>{historical ? "保留的旅行日程" : "已确认的日程"}</h2><p className="journeys-muted">{historical ? "过去保存的活动、时间与路线。" : "候选调整只有在你明确采用后，才会替换这里的安排。"}</p></div><button onClick={() => void load()}>刷新</button></div><div className="journeys-tabs" role="tablist" aria-label="旅行日期">{days.map((d, index) => <button role="tab" aria-selected={shownDay?.id === d.id} key={d.id} className={shownDay?.id === d.id ? "selected" : ""} onClick={() => setSelection({ ...selection, day: d.id })}>第{index + 1}天<span>{d.date}</span></button>)}</div>{shownDay ? <article className="journeys-card"><h3>{shownDay.theme || shownDay.label || shownDay.date}</h3>{shownDay.activities.length ? <ol className="journeys-activities">{shownDay.activities.map((a, i) => { const status = progress?.execution.activities.find(e => e.activityId === a.id)?.status; const executionActive = !historical && progress?.execution.status === "in_progress" && progress.execution.currentDayPlanId === shownDay.id && progress.execution.currentActivityId === a.id; return <li key={a.id}><div className="journeys-activity-top"><strong><Clock3 size={15} />{a.scheduledTime.slice(0, 5)}</strong><h4>{a.name}</h4>{status && <span className="journeys-chip">{executionLabels[status]}</span>}</div><p>停留{a.durationMinutes}分钟 · 规划费用 ¥{(a.estimatedCostFen / 100).toFixed(2)}{a.scheduleLocked && " · 时间已锁定"}</p>{a.note && <p>{a.note}</p>}<div className="journeys-actions">{onRoute && a.coordinates.every(Number.isFinite) && <button onClick={() => route(a, shownDay.activities[i - 1])}><Navigation size={14} />查询路线</button>}{executionActive && status === "pending" && <><button disabled={busy} onClick={() => action("arrive", a.id)}>我已到达</button><button disabled={busy || a.canSkip === false} onClick={() => action("skip", a.id)}>跳过这站</button></>}{executionActive && status === "arrived" && <button className="journeys-primary" disabled={busy} onClick={() => action("start_activity", a.id)}>开始体验</button>}{executionActive && status === "in_progress" && <><button className="journeys-primary" disabled={busy} onClick={() => action("complete", a.id)}>完成这站</button>{progress?.currentActivityExperience?.activityId === a.id && progress.currentActivityExperience.activityExecutionId && <><button disabled={busy} onClick={() => void perform(() => api.extendStay(progress.currentActivityExperience!.activityExecutionId, 15, crypto.randomUUID()), "已记录多停留15分钟，正在检查后续影响。")}>再停留15分钟</button><label className="journeys-extension">延长停留<select aria-label="延长停留分钟" disabled={busy} value={extension} onChange={e => setExtension(Number(e.target.value))}>{[15, 30, 60, 120, 240, 480].map(minutes => <option key={minutes} value={minutes}>{minutes}分钟</option>)}</select></label><button disabled={busy} onClick={() => void perform(() => api.extendStay(progress.currentActivityExperience!.activityExecutionId, extension, crypto.randomUUID()), `已记录多停留${extension}分钟，正在检查后续影响。`)}>确认延长停留</button><button disabled={busy} onClick={() => void perform(() => api.leaveEarly(progress.currentActivityExperience!.activityExecutionId, crypto.randomUUID()), "已记录提前离开，正在检查后续安排。")}>提前离开</button></>}</>}</div>{shownDay.routeLegs?.filter(l => l.fromActivityId === a.id).map((leg, n) => <p className="journeys-route-leg" key={n}>前往下一站 · {leg.mode === "walk" ? "步行" : leg.mode === "driving" ? "驾车" : "公交"} {leg.durationMinutes}分钟 / {(leg.distanceMeters / 1000).toFixed(1)}公里{leg.isEstimated ? " · 估算" : ""}</p>)}</li>; })}</ol> : <p>这一天尚未采用活动方案。</p>}{shownDay.conflicts?.map(c => <p className="journeys-notice" key={c.activityId}>{c.message}</p>)}</article> : <div className="journeys-empty">这次旅行暂时没有可读取的日程。</div>}</section>
    {!historical && <><section className="journeys-card journeys-preparation"><h2>{phase === "upcoming" ? "出发前核对" : "随身需要的信息"}</h2>{trip.accommodation ? <p>住宿记录：{trip.accommodation}{trip.accommodationAddress && ` · ${trip.accommodationAddress}`}</p> : <p>尚未记录住宿，请在出发前自行确认。</p>}<p>营业时间、门票和预约需再次核实。这里没有实时库存或预订确认。</p></section>
    {revisions.filter(r => r.id !== recoveryRevision?.id).map(revision => <section className="journeys-card journeys-candidate" key={revision.id} aria-label="候选日程差异"><h2>核对建议，再决定是否采用</h2><p>{revision.reason}</p><RevisionDifference revision={revision} days={days} names={names} /><div className="journeys-actions"><button className="journeys-primary" disabled={busy} onClick={() => void perform(() => api.acceptPlanRevision(revision.id), "已采用确认后的日程。")}>确认采用这份调整</button><button disabled={busy} onClick={() => void perform(() => api.rejectPlanRevision(revision.id), "已保留原日程。")}>保持原案</button></div></section>)}
    {runs.filter(r => r.status === "awaiting_clarification").map(run => <section className="journeys-card" key={run.id}><h2>还需要你补充一点</h2>{run.pendingInterrupt?.questions?.map(q => <p key={q}>{q}</p>)}<textarea aria-label="补充旅行要求" value={selection.clarification} onChange={e => setSelection({ ...selection, clarification: e.target.value })} /><button disabled={busy || !selection.clarification.trim()} onClick={() => void perform(() => api.answerPlanningRun(run.id, selection.clarification), "补充已提交，继续准备方案。")}>提交补充</button></section>)}
    <section className="journeys-card" aria-label="提出正式日程调整"><h2>{allActivities.length ? "想调整已经确认的安排？" : "准备这次旅行的活动安排"}</h2><p>写下具体要求，先生成候选方案。你的正式日程会保持原样，直到你明确确认采用。</p><label>调整范围<select value={selection.scope} onChange={e => setSelection({ ...selection, scope: e.target.value, activity: "" })}><option value="all">整段旅行</option>{days.map((d, i) => <option key={d.id} value={d.id}>仅第{i + 1}天 · {d.date}</option>)}</select></label><label>具体活动（可不选）<select aria-label="具体活动" value={selectedActivity?.id || ""} onChange={e => setSelection({ ...selection, activity: e.target.value, scope: e.target.value && adjustmentDay ? adjustmentDay.id : selection.scope })}><option value="">不指定活动</option>{adjustmentDay?.activities.map(a => <option key={a.id} value={a.id}>{a.scheduledTime.slice(0, 5)} · {a.name}</option>)}</select></label><label>希望怎样调整<textarea maxLength={3000} value={selection.request} onChange={e => setSelection({ ...selection, request: e.target.value })} placeholder="例如：第二天晚一点出门，保留已经确认的重要活动" /></label><button className="journeys-primary" disabled={busy || !selection.request.trim() || runs.some(inFlight) || revisions.length > 0} onClick={() => void propose()}>{runs.some(inFlight) ? "正在准备候选方案…" : "准备候选方案"}</button>{revisions.length > 0 && <p>请先决定已有候选方案，避免同时修改。</p>}{terminalFailure && !runs.some(inFlight) && <p role="alert">最近一次方案未完成：{terminalFailure.errorMessage || "服务暂不可用，可重试。"} 原日程保持不变。</p>}</section></>}
  </main>;
}
function RevisionDifference({ revision, days, names }: { revision: PlanRevision; days: DayPlan[]; names: Record<string, string> }) {
  const proposedDates = Array.from(new Set(revision.activities.map(a => a.dayDate)));
  const dates = Array.from(new Set([...days.map(d => d.date), ...proposedDates]));
  return <div className="journeys-diff">{dates.map(date => { const old = days.find(d => d.date === date); const next = revision.activities.filter(a => a.dayDate === date); const targets = revision.planningGoals?.targetDays; const unchanged = targets?.length && !targets.includes(date); return <article key={date}><h3>{date}{unchanged ? " · 保持原样" : ""}</h3>{!unchanged && <div className="journeys-diff-columns"><div><h4>当前已确认</h4>{old?.activities.length ? old.activities.map(a => <p key={a.id}>{a.scheduledTime.slice(0, 5)} {a.name} · {a.durationMinutes}分钟</p>) : <p>尚无活动</p>}</div><div><h4>候选安排</h4>{next.length ? next.map(a => <p key={a.candidateId}>{a.plannedStartTime.slice(0, 5)} {a.placeName || names[a.placeCandidateId] || old?.activities.find(o => o.placeId === a.placeCandidateId)?.name || "地点名称暂不可读，请刷新后核对"} · {a.durationMinutes}分钟{a.reason && ` · ${a.reason}`}</p>) : <p>没有候选活动，请确认是否清空这一天。</p>}</div></div>}</article>; })}</div>;
}



