import { Check, LoaderCircle, Send, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { DayPlan, PlaceCandidate, PlanRevision, PlanningRun, TripPlanningRepository } from "../domain/types";
import { formatFen } from "../utils/planner";

const WORKING = new Set(["queued", "researching", "planning", "validating"]);

export function AiPlannerPanel({ open, tripId, days, candidates, repository, onClose, onAccepted }: {
  open: boolean;
  tripId: string;
  days: DayPlan[];
  candidates: PlaceCandidate[];
  repository: TripPlanningRepository;
  onClose: () => void;
  onAccepted: () => Promise<void>;
}) {
  const [request, setRequest] = useState("请调整第2天下午的行程，节奏更轻松，减少步行并控制预算。");
  const [run, setRun] = useState<PlanningRun | null>(null);
  const [revision, setRevision] = useState<PlanRevision | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!run || !WORKING.has(run.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await repository.getPlanningRun(run.id);
        setRun(next);
        if (next.status === "awaiting_confirmation") setRevision(await repository.getPlanRevision(next.id));
      } catch (cause) { setError(messageOf(cause)); }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [repository, run]);

  const names = useMemo(() => new Map([
    ...candidates.map((item) => [item.id, item.name] as const),
    ...days.flatMap((day) => day.activities.map((item) => [item.placeId, item.name] as const)),
  ]), [candidates, days]);

  if (!open) return null;
  const start = async () => {
    if (!request.trim() || busy) return;
    setBusy(true); setError(null); setRevision(null);
    try {
      const next = await repository.createPlanningRun(tripId, request.trim());
      setRun(next);
      if (next.status === "awaiting_confirmation") setRevision(await repository.getPlanRevision(next.id));
    } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); }
  };
  const clarify = async () => {
    if (!run || !answer.trim() || busy) return;
    setBusy(true); setError(null);
    try { setRun(await repository.answerPlanningRun(run.id, answer.trim())); setAnswer(""); }
    catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); }
  };
  const decide = async (decision: "accept" | "reject") => {
    if (!revision || busy) return;
    setBusy(true); setError(null);
    try {
      const next = decision === "accept" ? await repository.acceptPlanRevision(revision.id) : await repository.rejectPlanRevision(revision.id);
      setRevision(next);
      setRun((current) => current ? { ...current, status: decision === "accept" ? "accepted" : "rejected" } : current);
      if (decision === "accept") await onAccepted();
    } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); }
  };

  return <div className="drawer-backdrop ai-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <aside className="ai-panel" aria-label="AI 规划助手">
      <header><div><span className="eyebrow">CONTEXT-AWARE AGENT</span><h2><Sparkles size={20} />AI 规划助手</h2><p>读取当前行程、偏好、路线与预算，先生成候选方案，确认后才写入。</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="关闭 AI 助手"><X size={18} /></button></header>
      <section className="ai-conversation">
        <div className="ai-message agent"><strong>你想怎样调整这次旅行？</strong><span>我会在当前杭州行程上规划，不会直接覆盖正式日程。</span></div>
        {run && <div className="ai-message user">{run.userRequest || request}</div>}
        {run && WORKING.has(run.status) && <div className="ai-message agent working"><LoaderCircle size={17} /><span>{statusText(run.status)}</span></div>}
        {run?.status === "awaiting_clarification" && <div className="ai-message agent"><strong>还需要确认一点</strong>{(run.pendingInterrupt?.questions ?? ["请补充你的偏好。 "]).map((question) => <span key={question}>{question}</span>)}<div className="ai-inline-input"><input value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="输入补充信息" /><button type="button" disabled={busy || !answer.trim()} onClick={() => void clarify()}><Send size={15} /></button></div></div>}
        {revision && <div className="ai-proposal"><div className="proposal-heading"><span>候选方案</span><i>{revision.status === "pending" ? "等待确认" : revision.status === "accepted" ? "已应用" : "已拒绝"}</i></div><p>{revision.reason || "已根据当前行程生成调整建议。"}</p><div className="proposal-list">{revision.activities.map((item) => <div key={item.candidateId}><time>{item.dayDate.slice(5)} {item.plannedStartTime}</time><span><strong>{names.get(item.placeCandidateId) ?? "行程地点"}</strong><small>{item.durationMinutes} 分钟 · {formatFen(item.estimatedCostFen)}</small></span></div>)}</div>{revision.status === "pending" && <div className="proposal-actions"><button type="button" disabled={busy} onClick={() => void decide("reject")}>暂不采用</button><button className="primary" type="button" disabled={busy} onClick={() => void decide("accept")}><Check size={15} />确认并应用</button></div>}</div>}
        {run?.status === "failed" && <div className="ai-message agent error">生成失败：{run.errorMessage ?? "请稍后重试"}</div>}
        {error && <div className="ai-message agent error">{error}</div>}
      </section>
      {!run || ["accepted", "rejected", "failed", "cancelled"].includes(run.status) ? <footer><textarea value={request} onChange={(event) => setRequest(event.target.value)} maxLength={4000} rows={3} /><button type="button" disabled={busy || !request.trim()} onClick={() => void start()}><Sparkles size={16} />{run ? "重新生成" : "生成调整方案"}</button><small>DeepSeek + LangGraph · 人工确认后写入 PostgreSQL</small></footer> : null}
    </aside>
  </div>;
}

function statusText(status: PlanningRun["status"]) {
  return ({ queued: "任务已进入队列…", researching: "正在整理地点与来源…", planning: "正在生成候选行程…", validating: "正在校验路线、时间与预算…" } as Record<string, string>)[status] ?? "正在处理…";
}

function messageOf(cause: unknown) { return cause instanceof Error ? cause.message : "AI 服务暂时不可用"; }
