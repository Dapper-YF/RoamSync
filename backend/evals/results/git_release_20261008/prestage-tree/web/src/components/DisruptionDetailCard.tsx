import { AlertTriangle, Info, Sparkles } from "lucide-react";
import type { ExecutionProgressQuery } from "../hooks/useExecutionProgress";
import { getDisruptionPresentation, getRecoveryLifecycle, selectDisruptionDetails } from "../utils/executionPresentation";

export function DisruptionDetailCard({ query }: { query: ExecutionProgressQuery }) {
  const progress = query.data;
  if (!progress) return null;
  if (progress.riskLevel === "disruption" && !progress.activeDisruption) return <section className="disruption-detail inconsistency" role="status"><Info size={17} /><div><strong>检测到执行风险，但详细信息暂不可用</strong><p>请稍后刷新以获取影响详情。</p></div></section>;
  if (!progress.activeDisruption) return null;
  const event = progress.activeDisruption;
  const presentation = getDisruptionPresentation(event);
  const details = selectDisruptionDetails(event);
  const lifecycle = getRecoveryLifecycle(progress.activeRecoveryRun, Boolean(progress.recoveryRevision));
  return <section className="disruption-detail" aria-label="行程影响详情">
    <header><span><AlertTriangle size={16} />行程影响详情</span><small>仍在持续</small></header>
    <strong>{presentation.title}</strong><p>{presentation.summary}</p>
    <dl><div><dt>影响活动或约束</dt><dd>{details.impact}</dd></div><div><dt>首次检测</dt><dd>{details.detectedAt}</dd></div><div><dt>最近确认</dt><dd>{details.lastSeenAt}</dd></div>{details.minimumSlack !== null && <div><dt>当前时间余量</dt><dd>{details.minimumSlack >= 0 ? `+${details.minimumSlack}` : details.minimumSlack} 分钟</dd></div>}</dl>
    <div className={`recovery-lifecycle tone-${lifecycle.tone}`}><Sparkles size={15} /><div><strong>{lifecycle.label}</strong><span>{lifecycle.message}</span></div></div>
    {query.isStale && <p className="disruption-stale">执行数据可能已过期，以上是最后一次已知影响。</p>}
  </section>;
}
