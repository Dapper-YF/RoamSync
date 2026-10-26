import type { ExecutionRiskState } from "../domain/types";
import type { RecoveryPlanningSummary, TripDisruptionSummary } from "../domain/types";

export interface ExecutionPresentation { tone: "quiet" | "notice" | "critical" | "unknown"; label: string; message: string; }

/** Maps backend truth to copy only; it never derives a risk state. */
export function getExecutionPresentation(risk: ExecutionRiskState): ExecutionPresentation {
  switch (risk) {
    case "normal": return { tone: "quiet", label: "行程正常", message: "当前尚未发现需要调整的行程问题。" };
    case "eta_delayed": return { tone: "notice", label: "预计到达有所延迟", message: "当前尚未检测到需要重新规划的问题。" };
    case "disruption": return { tone: "critical", label: "当前计划已受到影响", message: "RoamSync 正在根据实际进度准备恢复方案。" };
    case "unknown": return { tone: "unknown", label: "执行状态暂不可确认", message: "暂时没有足够的执行数据可以确认当前状态。" };
  }
}

export function formatClockTime(value?: string): string { return value ? new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value)) : "暂未获得"; }
export function formatDistance(value?: number): string { return value === undefined ? "暂未获得" : value >= 1000 ? `${(value / 1000).toFixed(1)} km` : `${value} m`; }
export function formatDelay(planned?: string, eta?: string): string | null { if (!planned || !eta) return null; const minutes = Math.round((Date.parse(eta) - Date.parse(planned)) / 60_000); return minutes > 0 ? `+${minutes} 分钟` : minutes < 0 ? `${minutes} 分钟` : "准时"; }
export function formatUpdated(value?: string | null): string { return value ? `更新于 ${formatClockTime(value)}` : "尚未更新"; }

export function getDisruptionPresentation(event: TripDisruptionSummary) {
  return event.eventType === "missed_time_window"
    ? { title: "预计无法按时到达", summary: "预计到达时间可能超过该活动的时间窗口。" }
    : { title: "当前行程已无法按原计划完成", summary: "当前延误已经影响后续正式行程约束。" };
}

export function selectDisruptionDetails(event: TripDisruptionSummary) {
  const minimumSlack = event.impactSnapshot.minimum_slack_minutes;
  return {
    impact: event.impactedIdentity,
    minimumSlack: typeof minimumSlack === "number" ? minimumSlack : null,
    detectedAt: formatClockTime(event.detectedAt), lastSeenAt: formatClockTime(event.lastSeenAt),
  };
}

export function getRecoveryLifecycle(run: RecoveryPlanningSummary | null, revisionReady: boolean) {
  if (revisionReady) return { label: "恢复方案已准备好", message: "下一步可查看恢复方案。", tone: "ready" };
  if (!run) return { label: "恢复规划尚未开始", message: "当前问题已确认，尚未创建恢复规划。", tone: "quiet" };
  if (run.status === "queued") return { label: "恢复规划已排队", message: "RoamSync 将开始分析剩余行程。", tone: "working" };
  if (["researching", "awaiting_clarification", "planning", "validating"].includes(run.status)) return { label: "正在生成恢复方案", message: "RoamSync 正在分析剩余行程并生成候选方案。", tone: "working" };
  if (run.status === "rejected") return { label: "之前的恢复方案已被拒绝", message: "当前风险仍然存在。", tone: "critical" };
  if (run.status === "failed") return { label: "恢复方案生成失败", message: run.errorMessage ?? "可稍后重试。", tone: "critical" };
  return { label: "恢复规划状态已更新", message: "当前问题仍在等待新的处理结果。", tone: "quiet" };
}
