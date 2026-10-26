import { Clock3, MapPin, Plus, SquareCheckBig } from "lucide-react";
import { useState } from "react";
import type { TripPlanningRepository } from "../domain/types";
import type { ExecutionProgressQuery } from "../hooks/useExecutionProgress";

const uuid = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
const time = (value?: string) => value ? new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(new Date(value)) : "—";

const statusPresentation = {
  pending: { label: "即将抵达", detail: "到达后即可开始记录实际游玩时间。" },
  arrived: { label: "已到达", detail: "确认开始游玩后，RoamSync 会持续感知停留时间。" },
  in_progress: { label: "正在游玩", detail: "延长或结束游玩会重新评估后续行程。" },
} as const;

/** Current-place controls. Navigation remains a separate concern. */
export function ActivityExperienceCard({ query, repository }: { query: ExecutionProgressQuery; repository: TripPlanningRepository }) {
  const [busy, setBusy] = useState(false);
  const progress = query.data;
  const experience = progress?.currentActivityExperience;
  const current = progress?.execution.activities.find((item) => item.activityId === progress.execution.currentActivityId);
  if (!progress || !current || !experience || !["pending", "arrived", "in_progress"].includes(current.status) || !progress.execution.id) return null;
  const run = async (action: () => Promise<unknown>) => { setBusy(true); try { await action(); await query.refresh(); } finally { setBusy(false); } };
  const impact = progress.experienceImpact;
  const activityStatus = current.status as keyof typeof statusPresentation;
  const presentation = statusPresentation[activityStatus];
  return <section className="experience-card" aria-label="当前活动体验">
    <header className="experience-header"><div><span className="experience-eyebrow"><MapPin size={13} />当前活动</span><strong>{progress.currentActivityName ?? current.name}</strong></div><span className={`experience-badge status-${current.status}`}>{presentation.label}</span></header>
    <p className="experience-description">{presentation.detail}</p>
    <div className="experience-facts"><div><small>计划停留</small><strong>{experience.plannedDurationMinutes} 分钟</strong></div>{current.status === "in_progress" && <div><small>已游玩</small><strong>{experience.elapsedExperienceMinutes ?? 0} 分钟</strong></div>}<div><small>已延长</small><strong>{experience.totalExtensionMinutes} 分钟</strong></div><div><small>预计结束</small><strong>{time(experience.projectedEndAt)}</strong></div></div>
    {current.status === "pending" ? <button className="experience-primary" disabled={busy} onClick={() => void run(() => repository.applyTripExecutionAction(progress.execution.id!, "arrive", current.activityId))}><MapPin size={15} />我已到达</button> : current.status === "arrived" ? <button className="experience-primary" disabled={busy} onClick={() => void run(() => repository.applyTripExecutionAction(progress.execution.id!, "start_activity", current.activityId))}><Clock3 size={15} />开始游玩</button> : <><div className="experience-actions">{[15, 30, 60].map((minutes) => <button key={minutes} disabled={busy} onClick={() => void run(() => repository.extendStay(experience.activityExecutionId, minutes, uuid()))}><Plus size={14} />再待 {minutes} 分钟</button>)}</div><button className="experience-complete" disabled={busy} onClick={() => void run(() => repository.leaveEarly(experience.activityExecutionId, uuid()))}><SquareCheckBig size={15} />结束游玩，前往下一站</button></>}
    {impact?.impactState === "absorbed" && <p className="experience-note"><Clock3 size={14} />这次延长可以由现有时间余量吸收，后续行程暂不需要修改。</p>}
    {impact?.impactState === "at_risk" && <p className="experience-note">后续时间余量有所减少，目前仍可继续原计划。最小余量：{impact.minimumDownstreamSlackMinutes ?? "—"} 分钟。</p>}
    {impact?.impactState === "infeasible" && <p className="experience-warning">继续停留会影响后续安排，RoamSync 正在根据新的离开时间调整行程。</p>}
  </section>;
}
