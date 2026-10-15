import { AlertTriangle, Check, CircleAlert, RefreshCw, X } from "lucide-react";
import { useState } from "react";
import { ApiRequestError } from "../data/apiTripPlanningRepository";
import type { TripPlanningRepository } from "../domain/types";
import type { ExecutionProgressQuery } from "../hooks/useExecutionProgress";

type MutationState = "idle" | "confirming" | "accepting" | "rejecting" | "conflict" | "error";

/** Decision support for a persisted PlanRevision; formal state stays server-owned. */
export function RecoveryPanel({ query, repository, onAccepted }: {
  query: ExecutionProgressQuery;
  repository: TripPlanningRepository;
  onAccepted: () => Promise<void>;
}) {
  const [state, setState] = useState<MutationState>("idle");
  const progress = query.data;
  const recovery = progress?.recoveryPlanning;
  const revision = recovery?.pendingRevision ?? (progress?.activeDisruption ? progress.recoveryRevision : null);
  if (recovery?.status === "superseded") return <section className="recovery-panel" role="status"><p>你的游览时间再次发生变化，之前的调整方案已失效。</p></section>;
  if (!revision || revision.status !== "pending") return recovery && ["queued", "planning"].includes(recovery.status) ? <section className="recovery-panel" role="status"><header><span><RefreshCw size={15} />行程调整</span></header><p>{recovery.reasonSummary}</p><p>RoamSync 正在准备新的后续安排…</p></section> : null;
  const busy = state === "accepting" || state === "rejecting";
  const stale = query.isStale;
  const count = numberFact(revision.differenceSummary, "candidate_activity_count");
  const budgetDelta = numberFact(revision.differenceSummary, "planned_budget_delta_fen");
  const verifiedDecisionExplanation = (revision.differenceSummary.decision_summary as { status?: string } | undefined)?.status === "validated";

  const accept = async () => {
    if (busy || stale) return;
    setState("accepting");
    try {
      await repository.acceptPlanRevision(revision.id);
      // The commit response is only mutation acknowledgement.  Read all server
      // state again; the formal itinerary and execution projection have distinct
      // read paths and neither is updated optimistically.
      await Promise.all([onAccepted(), query.refresh()]);
      setState("idle");
    } catch (cause) {
      if (cause instanceof ApiRequestError && cause.status === 409) {
        setState("conflict");
        await Promise.allSettled([onAccepted(), query.refresh()]);
      } else setState("error");
    }
  };
  const reject = async () => {
    if (busy || stale) return;
    setState("rejecting");
    try { await repository.rejectPlanRevision(revision.id); await query.refresh(); setState("idle"); }
    catch { setState("error"); }
  };

  const experience = recovery?.source === "activity_experience";
  return <section className="recovery-panel" aria-label="恢复方案">
    <header><span><RefreshCw size={15} />{experience ? "行程调整方案" : "恢复方案"}</span><small>待你确认</small></header>
    {experience && <p className="recovery-explanation">你选择继续停留后，当前正在游览的 {recovery.triggerActivityName ?? "活动"} 将保持不变，本方案只调整后续安排。</p>}
    <div className="recovery-facts">
      {count !== null && <div><small>候选安排</small><strong>{count} 项</strong></div>}
      {budgetDelta !== null && <div><small>计划费用变化</small><strong>{formatFenDelta(budgetDelta)}</strong></div>}
    </div>
    <section className="recovery-section" aria-label="恢复后安排"><h3>恢复后安排</h3><ul className="recovery-activities">{revision.proposedSnapshot.activities.map((activity) => <li key={activity.candidateId}><strong>{activity.placeName ?? "候选地点"}</strong><span>{activity.dayDate.slice(5)} · {activity.plannedStartTime} · {activity.durationMinutes} 分钟</span>{verifiedDecisionExplanation && activity.reason && <small>{activity.reason}</small>}</li>)}</ul></section>
    {revision.changeSummary.adjustedActivities.length > 0 && <section className="recovery-section" aria-label="行程变化"><h3>行程变化</h3><ul className="recovery-changes">{revision.changeSummary.adjustedActivities.map((change) => <li key={change.activityId}><strong>{change.name ?? "既有活动"}</strong><span>{change.beforeStartTime} · {change.beforeDurationMinutes ?? "—"} 分钟 → {change.afterStartTime} · {change.afterDurationMinutes ?? "—"} 分钟</span></li>)}</ul></section>}
    {verifiedDecisionExplanation && (revision.proposedSnapshot.explanation || revision.reason) ? <section className="recovery-explanation"><h3>方案说明</h3><p>{revision.proposedSnapshot.explanation || revision.reason}</p></section> : <p className="recovery-explanation">调整原因暂未通过核验</p>}
    {stale && <p className="recovery-warning" role="status"><AlertTriangle size={14} />执行数据可能已过期，请刷新后再应用方案。<button type="button" onClick={() => void query.refresh()}>重新检查</button></p>}
    {state === "conflict" && <p className="recovery-warning" role="alert"><CircleAlert size={14} />行程已经发生变化，该恢复方案已过期。</p>}
    {state === "error" && <p className="recovery-warning" role="alert"><CircleAlert size={14} />暂时无法应用该方案，请检查网络后重试。</p>}
    {state === "confirming" ? <div className="recovery-confirm"><span>应用该方案将修改正式行程。</span><button type="button" onClick={() => setState("idle")}>取消</button><button type="button" className="primary" onClick={() => void accept()}>确认应用</button></div> : <div className="recovery-actions"><button type="button" disabled={busy || stale} onClick={() => setState("confirming")}>{busy ? "正在处理…" : "采用方案"}</button><button type="button" disabled={busy || stale} onClick={() => void reject()}>{busy ? "正在处理…" : "拒绝方案"}</button></div>}
    {state === "accepting" && <p className="recovery-pending"><Check size={14} />正在读取更新后的正式行程…</p>}
    {state === "rejecting" && <p className="recovery-pending"><X size={14} />正在保留当前正式行程…</p>}
  </section>;
}

function numberFact(values: Record<string, unknown>, key: string): number | null {
  const value = values[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function formatFenDelta(value: number) { return `${value >= 0 ? "+" : "−"}¥${(Math.abs(value) / 100).toFixed(2)}`; }
