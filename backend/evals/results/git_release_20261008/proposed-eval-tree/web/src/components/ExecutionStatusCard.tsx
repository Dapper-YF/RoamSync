import { AlertTriangle, CheckCircle2, CircleHelp, Clock3, Navigation, RefreshCw, Route } from "lucide-react";
import type { ExecutionProgressQuery } from "../hooks/useExecutionProgress";
import { formatClockTime, formatDelay, formatDistance, formatUpdated, getExecutionPresentation } from "../utils/executionPresentation";

export function ExecutionStatusCard({ query, onStartTrip, startingTrip = false }: { query: ExecutionProgressQuery; onStartTrip?: () => void; startingTrip?: boolean }) {
  if (query.isInitialLoading && !query.data) return <section className="execution-card execution-loading" aria-busy="true"><span className="execution-skeleton" /><span className="execution-skeleton short" /></section>;
  const progress = query.data;
  if (!progress) return <section className="execution-card execution-empty"><CircleHelp size={18} /><div><strong>当前没有进行中的导航</strong><p>{query.error ? "暂时无法读取执行状态，请稍后重试。" : "开始执行旅行后，这里会显示当前路段和预计到达时间。"}</p></div></section>;
  const session = progress.navigationSession;
  if (!session) return <section className="execution-card execution-empty"><Navigation size={18} /><div><strong>{progress.execution.status === "not_started" ? "行程尚未开始" : "当前没有正在执行的路段"}</strong>{progress.execution.status === "not_started" && <><p>当前第一站：{progress.currentActivityName ?? "待确认"}</p><button type="button" disabled={!onStartTrip || startingTrip} onClick={onStartTrip}>{startingTrip ? "正在开始行程…" : "开始行程"}</button></>}<p>{formatUpdated(progress.generatedAt)}</p></div></section>;
  const display = getExecutionPresentation(progress.riskLevel);
  const delay = formatDelay(session.plannedArrivalAt, session.currentEta);
  const icon = display.tone === "critical" ? <AlertTriangle size={17} /> : display.tone === "unknown" ? <CircleHelp size={17} /> : <CheckCircle2 size={17} />;
  return <section className={`execution-card tone-${display.tone}`} aria-label="当前行程执行状态">
    <header><span className="execution-eyebrow"><Navigation size={13} />正在前往</span><span className="execution-badge">{icon}{display.label}</span></header>
    <strong className="execution-target">{progress.navigationTargetName ?? "下一站"}</strong>
    <p className="execution-message">{display.message}</p>
    <div className="execution-times"><div><small>计划到达</small><strong>{formatClockTime(session.plannedArrivalAt)}</strong></div><div><small>预计到达</small><strong>{formatClockTime(session.currentEta)}</strong></div>{delay && <div><small>到达差异</small><strong>{delay}</strong></div>}</div>
    <footer><span><Route size={13} />剩余 {formatDistance(session.remainingDistanceMeters)}</span><span><Clock3 size={13} />{formatUpdated(progress.generatedAt)}</span>{query.isRefreshing && <span><RefreshCw size={12} />正在更新</span>}</footer>
    {query.isStale && <p className="execution-stale" role="status">数据更新可能已延迟：{query.error?.message ?? "请稍后刷新"}</p>}
    {progress.riskLevel === "disruption" && progress.activeDisruption && <p className="execution-impact"><strong>{progress.activeDisruption.eventType === "itinerary_infeasible" ? "当前行程已无法按原计划完成" : "可能错过计划时间窗口"}</strong><span>影响：{progress.activeDisruption.impactedIdentity} · {progress.recoveryRevision ? "恢复方案已准备好" : progress.activeRecoveryRun ? "正在准备恢复方案" : "等待恢复方案"}</span></p>}
  </section>;
}
