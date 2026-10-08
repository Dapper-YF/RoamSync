import { Activity, ArrowUp, Check, ChevronDown, Compass, History, Leaf, LoaderCircle, RotateCcw, Send, ShieldCheck, Sparkles, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { AssistantSession, DayPlan, ExternalFacts, PlaceCandidate, PlanRevision, PlanningRun, TripPlanningRepository } from "../domain/types";
import { formatFen } from "../utils/planner";
import { ResearchEvidence } from "./ResearchEvidence";
import { CompanionThinking, companionAnswer } from "./CompanionThinking";
import { PlanningFailure } from "./PlanningFailure";
import { PlanningProgress } from "./PlanningProgress";
import { PlanningGoalCard } from "./PlanningGoalCard";
import { DecisionSummary } from "./DecisionSummary";
import { planningErrorMessage } from "../utils/planningMessages";
import { publishMonitor } from "../utils/agentMonitorChannel";

const WORKING = new Set(["queued", "researching", "planning", "validating"]);

export function AiPlannerPanel({ open, tripId: requestedTripId, days, candidates, repository, onClose, onAccepted, onTripChanged, selectedDayId, selectedActivityId }: {
  open: boolean;
  selectedDayId?: string;
  selectedActivityId?: string;
  tripId?: string;
  days: DayPlan[];
  candidates: PlaceCandidate[];
  repository: TripPlanningRepository;
  onClose: () => void;
  onAccepted: () => Promise<void>;
  onTripChanged?: (tripId: string) => Promise<void> | void;
}) {
  const tripId = requestedTripId ?? "";
  const [assistantSession, setAssistantSession] = useState<AssistantSession | null>(null);
  const lastSubmission = useRef<{ text: string; id: string } | null>(null);
  const [submission, setSubmission] = useState<{ text: string; failed?: boolean } | null>(null);
  const [request, setRequest] = useState("");
  const [run, setRun] = useState<PlanningRun | null>(null);
  const [revision, setRevision] = useState<PlanRevision | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedPlanError, setSavedPlanError] = useState<string | null>(null);
  const [history, setHistory] = useState<PlanningRun[]>([]);
  const [externalFacts, setExternalFacts] = useState<ExternalFacts>({});
  const [rejecting, setRejecting] = useState(false);
  const [rejectionReasonCode, setRejectionReasonCode] = useState<PlanRevision["rejectionReasonCode"]>();
  const [rejectionReasonText, setRejectionReasonText] = useState("");

  const [checking, setChecking] = useState(false);
  const [resolvedCandidates, setResolvedCandidates] = useState<PlaceCandidate[]>([]);
  const [historyReady, setHistoryReady] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const composing = useRef(false);
  const hasPlan = days.some((day) => day.activities.length > 0);
  const pending = Boolean(run && !["accepted", "rejected", "failed", "cancelled", "answered"].includes(run.status));
  const inputBlocked = Boolean(run && WORKING.has(run.status));
  const workingRunId = run && WORKING.has(run.status) ? run.id : undefined;
  const conversationEnd = useRef<HTMLDivElement>(null);
  useEffect(() => { conversationEnd.current?.scrollIntoView?.({ block: "nearest" }); }, [submission?.text, assistantSession?.messages.length, run?.id, run?.progress?.stage]);
  const sendOnEnter = (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>, send: () => void) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing || composing.current || event.keyCode === 229) return;
    event.preventDefault();
    if (!event.repeat) send();
  };

  const syncRun = useCallback(async (next: PlanningRun) => {
    setSavedPlanError(null);
    setRun(next);
    setHistory((items) => [next, ...items.filter((item) => item.id !== next.id)]);
    setRevision(null);
    if (["awaiting_confirmation", "accepted", "rejected"].includes(next.status)) {
      setRevision(await repository.getPlanRevision(next.id));
      setResolvedCandidates(await repository.getCandidates(tripId));
    }
  }, [repository, tripId]);

  // Restore the session's explicit run across creation navigation/refresh.
  // Companion-only sessions still load no planning history or context.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setChecking(true);
    setHistoryReady(false);
    setHistory([]);
    setHistoryLoaded(false);
    setRun(null);
    setRevision(null);
    setExternalFacts({});
    (async () => {
      if (repository.getAssistantSession) {
        const session = await repository.getAssistantSession(requestedTripId);
        if (cancelled) return;
        setAssistantSession(session);
        if (requestedTripId && session.latest_run_id) {
          const restored = await repository.getPlanningRun(session.latest_run_id);
          if (cancelled) return;
          if (restored.tripId !== requestedTripId) throw new Error("规划任务不属于当前旅行，请重新读取对话。");
          let restoredRevision: PlanRevision | null = null;
          let restoredCandidates: PlaceCandidate[] = [];
          if (["awaiting_confirmation", "accepted", "rejected"].includes(restored.status)) {
            [restoredRevision, restoredCandidates] = await Promise.all([
              repository.getPlanRevision(restored.id), repository.getCandidates(requestedTripId),
            ]);
          }
          if (cancelled) return;
          setRun(restored);
          setHistory([restored]);
          setRevision(restoredRevision);
          setResolvedCandidates(restoredCandidates);
        }
      }
      if (!cancelled) setHistoryReady(true);
    })().catch((cause) => { if (!cancelled) setError(messageOf(cause)); })
      .finally(() => { if (!cancelled) setChecking(false); });
    return () => { cancelled = true; };
  }, [open, repository, requestedTripId]);

  const loadPlanningHistory = async () => {
    if (!tripId || historyLoaded || historyLoading) return;
    setHistoryLoading(true);
    try {
      const items = await repository.listPlanningRuns(tripId);
      setHistory(items);
      setHistoryLoaded(true);
      if (items[0]) {
        await syncRun(items[0]);
        await loadPlanningContext();
      }
    } catch (cause) {
      setError(messageOf(cause));
    } finally {
      setHistoryLoading(false);
    }
  };

  const loadPlanningContext = async () => {
    if (!tripId) return;
    try {
      const context = await repository.getPlanningContext(tripId);
      setExternalFacts(context.externalFacts ?? {});
    } catch {
      setExternalFacts({});
    }
  };

  useEffect(() => {
    if (!workingRunId) return;
    let cancelled = false;
    let timer: number;
    const poll = async () => {
      try {
        const next = await repository.getPlanningRun(workingRunId);
        if (!cancelled) { setError(null); await syncRun(next); }
      } catch (cause) { if (!cancelled) setError(messageOf(cause)); }
      finally { if (!cancelled) timer = window.setTimeout(poll, 1500); }
    };
    timer = window.setTimeout(poll, 1500);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [repository, workingRunId, syncRun]);

  const names = useMemo(() => new Map([
    ...resolvedCandidates.map((item) => [item.id, item.name] as const),
    ...candidates.map((item) => [item.id, item.name] as const),
    ...days.flatMap((day) => day.activities.map((item) => [item.placeId, item.name] as const)),
  ]), [candidates, days, resolvedCandidates]);

  if (!open) return null;
  const start = async (retryRequest?: string, retryRun?: PlanningRun) => {
    const message = (retryRequest ?? request).trim();
    if (!message || busy || inputBlocked || checking || !historyReady) return;
    setBusy(true); setError(null); setRevision(null);
    setSubmission({ text: message }); setRequest("");
    const observationId = crypto.randomUUID();
    if (!retryRun && assistantSession && repository.sendAssistantMessage && lastSubmission.current?.text !== message) {
      lastSubmission.current = { text: message, id: crypto.randomUUID() };
    }
    let requestReturned = false;
    publishMonitor({ type: "request_started", requestId: observationId, tripId, message,
      sessionId: !retryRun ? assistantSession?.id : undefined, messageId: !retryRun ? lastSubmission.current?.id : undefined });
    try {
      if (!retryRun && assistantSession && repository.sendAssistantMessage) {
        if (lastSubmission.current?.text !== message) lastSubmission.current = { text: message, id: crypto.randomUUID() };
        const next = await repository.sendAssistantMessage(assistantSession.id, message, lastSubmission.current.id, selectedDayId, selectedActivityId);
        const actualMessage = next.messages.find((item) => item.id === lastSubmission.current?.id);
        requestReturned = true;
        publishMonitor({ type: "request_completed", requestId: observationId, tripId: next.trip_id ?? undefined,
          runId: !actualMessage?.companion_result && ["plan_trip", "query_trip"].includes(String((actualMessage as unknown as { tool?: string })?.tool)) ? actualMessage?.run_id ?? undefined : undefined, assistant: actualMessage?.assistant,
          runtimeTrace: actualMessage?.companion_result?.runtime_trace });
        setAssistantSession(next); setRun(null); setSubmission(null); lastSubmission.current = null;
        if (next.trip_id && next.trip_id !== tripId) { await onTripChanged?.(next.trip_id); return; }
        if (next.latest_run_id) {
          await syncRun(await repository.getPlanningRun(next.latest_run_id));
          await loadPlanningContext();
        }
        return;
      }
      const next = await repository.createPlanningRun(retryRun?.tripId ?? tripId, message, {
        runType: retryRun?.runType ?? (hasPlan ? "replan" : "initial_plan"),
        selectedDayId: hasPlan ? selectedDayId : undefined,
        selectedActivityId: hasPlan ? selectedActivityId : undefined,
      });
      requestReturned = true;
      await syncRun(next);
      await loadPlanningContext();
      publishMonitor({ type: "request_completed", requestId: observationId, tripId: next.tripId, runId: next.id });
      setSubmission(null);
    } catch (cause) { if (!requestReturned) publishMonitor({ type: "request_failed", requestId: observationId, tripId, error: messageOf(cause) }); setError(messageOf(cause)); setSubmission((value) => value ? { ...value, failed: true } : null); setRequest(message); } finally { setBusy(false); }
  };
  const clearConversation = async () => {
    if (tripId || !assistantSession || !repository.resetAssistantSession || busy || checking) return;
    setBusy(true); setError(null);
    try {
      const fresh = await repository.resetAssistantSession(assistantSession.id);
      setAssistantSession(fresh);
      lastSubmission.current = null;
      setSubmission(null); setRequest(""); setAnswer("");
      setRun(null); setRevision(null); setHistory([]); setExternalFacts({});
      setSavedPlanError(null); setResolvedCandidates([]);
      setRejecting(false); setRejectionReasonCode(undefined); setRejectionReasonText("");
    } catch (cause) { setError(messageOf(cause)); }
    finally { setBusy(false); }
  };
  const applyAssistantAction = async (accept: boolean) => {
    if (!assistantSession?.pending_action || !repository.decideAssistantAction || busy) return;
    setBusy(true); setError(null);
    try {
      const next = await repository.decideAssistantAction(assistantSession.id, assistantSession.pending_action.id, accept);
      setAssistantSession(next); setRun(null); setRevision(null);
      if (accept && next.trip_id) await onTripChanged?.(next.trip_id);
      if (next.latest_run_id && next.trip_id === tripId) await syncRun(await repository.getPlanningRun(next.latest_run_id));
    } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); }
  };
  const restore = async (item: PlanningRun) => {
    setBusy(true); setError(null); setRevision(null);
    try {
      const next = await repository.getPlanningRun(item.id);
      await syncRun(next);
      await loadPlanningContext();
      setHistoryReady(true);
    } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); }
  };
  const clarify = async () => {
    if (!run || !answer.trim() || busy) return;
    setBusy(true); setError(null);
    try { await syncRun(await repository.answerPlanningRun(run.id, answer.trim())); setAnswer(""); }
    catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); }
  };
  const viewSavedPlan = async () => {
    setBusy(true); setSavedPlanError(null);
    try { await onAccepted(); }
    catch (cause) { setSavedPlanError(messageOf(cause)); }
    finally { setBusy(false); }
  };
  const decide = async (decision: "accept") => {
    if (!revision || busy) return;
    setBusy(true); setError(null);
    try {
      if (!run) return;
      const result = await repository.decidePlanningRun(run.id, decision);
      setRevision(result.revision);
      setRun(result.run);
      setHistory((items) => [result.run, ...items.filter((item) => item.id !== result.run.id)]);
      if (result.run.status !== "accepted" || result.revision.status !== "accepted") {
        throw new Error("方案尚未保存到正式行程，请检查当前方案状态后重试。");
      }
      await viewSavedPlan();
    } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); }
  };
  const rejectWithFeedback = async () => {
    if (!revision || !rejectionReasonCode || busy) return;
    setBusy(true); setError(null);
    try {
      const rejected = await repository.rejectPlanRevision(revision.id, {
        reasonCode: rejectionReasonCode, reasonText: rejectionReasonText,
      });
      setRevision(rejected);
      if (run) {
        const next = { ...run, status: "rejected" as const };
        setRun(next); setHistory((items) => [next, ...items.filter((item) => item.id !== next.id)]);
      }
      setRejecting(false); setRejectionReasonCode(undefined); setRejectionReasonText("");
    } catch (cause) { setError(messageOf(cause)); } finally { setBusy(false); }
  };

  const verifiedDecisionExplanation = (revision?.differenceSummary.decision_summary as { status?: string } | undefined)?.status === "validated";
  return <div className="drawer-backdrop ai-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <aside className="ai-panel" aria-label="旅程总管">
      <header>
        <div className="ai-heading">
          <div className="ai-avatar" aria-hidden="true"><Compass size={26} strokeWidth={1.6} /></div>
          <div><span className="eyebrow">旅行对话助手</span><h2>旅程总管</h2></div>
        </div>
        <div className="ai-header-actions">{!tripId && repository.resetAssistantSession && <button className="ai-reset" type="button" onClick={() => void clearConversation()} disabled={busy || checking || !assistantSession} aria-label="清除对话" title="清除当前对话，重新聊一趟旅行"><RotateCcw size={15} /><span>清除对话</span></button>}<a className="ai-monitor-link" href={tripId ? `/dev/agent-monitor?trip=${encodeURIComponent(tripId)}` : "/dev/agent-monitor"} target="_blank" rel="noreferrer" aria-label="打开监控台"><Activity size={15} />打开监控台</a><button className="ai-close" type="button" onClick={onClose} aria-label="关闭旅程总管"><X size={19} /></button></div>
        <p>聊聊目的地、旅行体验，也可以问问旅途中的问题。</p>
        <span className="ai-context-tag"><span aria-hidden="true" />{tripId ? "围绕这趟旅行，随时聊聊" : "从一个想法，到下一次出发"}</span>
      </header>
      <section className="ai-conversation">
        <div className="ai-welcome"><span className="ai-welcome-mark" aria-hidden="true"><Sparkles size={17} /></span><div><strong>{hasPlan ? "这趟旅行，有什么想聊的？" : "今天想聊点什么？"}</strong><p>{hasPlan ? "可以聊目的地、旅行体验或目前安排；想调整行程时，再告诉我具体想法。" : "可以聊聊目的地、旅行灵感和出行方式，想规划时再告诉我。"}</p></div></div>
        {tripId && <details className="ai-history" onToggle={(event) => { if (event.currentTarget.open) void loadPlanningHistory(); }}><summary><History size={15} aria-hidden="true" /><span>对话与方案记录</span>{historyLoaded && <span className="ai-history-count">{history.length}</span>}<ChevronDown size={15} aria-hidden="true" /></summary>{historyLoading && <div className="directory-state"><span className="spinner" />正在读取方案记录…</div>}{historyLoaded && history.length === 0 && <p className="ai-history-empty">暂时没有规划记录。</p>}<div className="ai-history-items">{history.map((item) => <button type="button" key={item.id} disabled={busy || checking || (inputBlocked && item.id !== run?.id)} onClick={() => void restore(item)}><span>{item.userRequest || "生成完整行程"}</span><i>{statusText(item.status)}</i></button>)}</div></details>}
        {history.filter((item) => item.status === "answered" && item.id !== run?.id && !assistantSession?.messages.some((message) => message.run_id === item.id)).slice(0, 3).reverse().map((item) => <div className="ai-exchange" key={item.id}><div className="ai-message user">{item.userRequest}</div><div className="ai-message agent ai-answer"><AnswerText text={item.responseText ?? ""} /></div></div>)}
        {assistantSession?.messages.slice(-10).map((item) => <div className="ai-exchange" key={item.id}><div className="ai-message user">{item.user}</div><div className="ai-message agent ai-answer"><AnswerText text={item.companion_result ? companionAnswer(item.assistant) : history.find((result) => result.id === item.run_id && result.status === "answered")?.responseText || item.assistant} />{item.companion_result && <CompanionThinking result={item.companion_result} />}</div></div>)}
        {assistantSession?.pending_action && <div className="ai-proposal assistant-action"><div className="proposal-heading"><span>{assistantSession.pending_action.tool === "reschedule_trip" ? "确认旅行改期" : "确认创建旅行"}</span><i>等待确认</i></div><h3>{assistantSession.pending_action.title}</h3><p>{assistantSession.pending_action.summary}</p>{assistantSession.pending_action.source_title && <p>参考旅行：{assistantSession.pending_action.source_title}</p>}<div className="proposal-impact"><span>目的地：{assistantSession.pending_action.city.name}</span><span>{assistantSession.pending_action.start_date} — {assistantSession.pending_action.end_date}</span><span>总预算：{formatFen(assistantSession.pending_action.total_budget_fen)}</span><span>每日预算：{formatFen(assistantSession.pending_action.daily_budget_fen)}</span></div>{assistantSession.pending_action.preferences && <p>{assistantSession.pending_action.preferences}</p>}<div className="proposal-actions"><button type="button" disabled={busy} onClick={() => void applyAssistantAction(false)}>暂不执行</button><button className="primary" type="button" disabled={busy} onClick={() => void applyAssistantAction(true)}>{assistantSession.pending_action.tool === "reschedule_trip" ? "确认改期" : "确认创建"}</button></div></div>}
        {run?.status === "awaiting_confirmation" && <p className="ai-pending-hint">方案等待确认期间，也可以继续提问或讨论理由。</p>}
        {run && !assistantSession?.messages.some((item) => item.run_id === run.id) && <div className="ai-message user">{run.userRequest || request}</div>}
        {run?.status === "answered" && !assistantSession?.messages.some((item) => item.run_id === run.id) && <div className="ai-message agent ai-answer"><AnswerText text={run.responseText ?? ""} /></div>}
        {submission && <div className="ai-exchange"><div className="ai-message user">{submission.text}</div>{submission.failed ? <div className="ai-message agent">本次请求尚未确认成功，内容已保留，可重试发送。</div> : <div className="ai-message agent working" role="status"><LoaderCircle size={17} /><span>正在回复…</span></div>}</div>}
        {run && WORKING.has(run.status) && <PlanningProgress run={run} />}
        {run?.decisionMemory && run.decisionMemory.feedback.length > 0 && <div className="ai-facts" aria-label="已参考上次反馈"><strong>已参考上次反馈</strong>{run.decisionMemory.feedback.map((item) => <span key={item.sourceRevisionId}>{item.reasonText?.trim() || rejectionReasonLabel(item.reasonCode)}</span>)}<small>仅显示本次规划实际检索到的同一行程反馈。</small></div>}
        {(externalFacts.weather || externalFacts.search) && <div className="ai-facts"><strong>本次规划参考</strong><span>天气：{factStatus(externalFacts.weather?.status)}{externalFacts.weather?.temperatureC != null ? ` · ${externalFacts.weather.temperatureC}°C` : ""}</span><span>搜索：{factStatus(externalFacts.search?.status)}{externalFacts.search?.results?.length ? ` · ${externalFacts.search.results.length} 条来源` : ""}</span><small>外部事实仅作为建议依据，最终仍需你确认。</small></div>}
        {run?.status === "awaiting_clarification" && <div className="ai-message agent"><strong>还需要确认一点</strong>{(run.pendingInterrupt?.questions ?? ["请补充你的偏好。 "]).map((question) => <span key={question}>{question}</span>)}<div className="ai-inline-input"><input onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }} onKeyDown={(event) => sendOnEnter(event, () => void clarify())} value={answer} onChange={(event) => setAnswer(event.target.value)} aria-label="补充回答" placeholder="输入补充信息" /><button type="button" disabled={busy || !answer.trim()} onClick={() => void clarify()}><Send size={15} /><span className="sr-only">提交补充</span></button></div></div>}
        {revision?.status === "rejected" && <div className="ai-message agent">已暂不采用这份方案。下一次规划会参考你刚才的反馈，并依据正式行程和新要求重新安排。</div>}
        {revision && revision.status !== "rejected" && <PlanningGoalCard revision={revision} />}
        {revision && revision.status !== "rejected" && <DecisionSummary revision={revision} />}
        {revision && revision.status !== "rejected" && <div className="ai-proposal"><div className="proposal-heading"><span>{revision.status === "accepted" ? "方案应用记录" : "候选方案"}</span><i>{revision.status === "pending" ? "等待确认" : revision.status === "accepted" ? "已保存到正式行程" : revision.status === "superseded" ? "已被新方案替代" : "已拒绝"}</i></div><strong className="proposal-rationale-title">为什么这样安排</strong><p className="proposal-rationale">{verifiedDecisionExplanation ? (revision.reason === "Agent planning candidate" ? "根据你的要求生成的行程建议" : revision.reason || "已根据当前行程生成调整建议。") : "AI生成的候选调整"}</p><div className="proposal-impact"><span>方案包含：{revision.activities.length} 项活动</span><span>预计支出：{typeof revision.differenceSummary.planned_total_fen === "number" ? formatFen(revision.differenceSummary.planned_total_fen) : "详见活动费用"}</span><span>较原行程：{moneyImpact(revision.differenceSummary)}</span><span>校验：{validationText(revision.validationResult)}</span><span>参考来源：{revision.sourceIds.length} 条</span></div>{Array.isArray(revision.differenceSummary.schedule_adjustments) && revision.differenceSummary.schedule_adjustments.length > 0 && <p className="proposal-adjustment">已按查询到的路线时长，为 {revision.differenceSummary.schedule_adjustments.length} 项活动补足交通时间。以下展示调整后的时间。</p>}<ResearchEvidence value={revision.differenceSummary.destination_research} /><div className="proposal-list">{revision.activities.map((item) => <div key={item.candidateId}><time>{item.dayDate.slice(5)} {item.plannedStartTime}</time><span><strong>{names.get(item.placeCandidateId) ?? "行程地点"}</strong><small>{item.durationMinutes} 分钟 · {formatFen(item.estimatedCostFen)}</small>{verifiedDecisionExplanation && item.reason && <p className="activity-rationale">{item.reason}</p>}</span></div>)}</div>{revision.activities.length === 0 && !hasPlan && <p role="alert">这份方案没有安排任何地点，不能作为首次行程保存。请暂不采用后重新规划。</p>}{revision.status === "pending" && <><div className="proposal-actions"><button type="button" disabled={busy} onClick={() => setRejecting(true)}>暂不采用</button><button className="primary" type="button" disabled={busy || (revision.activities.length === 0 && !hasPlan)} onClick={() => void decide("accept")}><Check size={15} />确认并应用</button></div>{rejecting && <div className="ai-inline-input" aria-label="拒绝方案反馈"><strong>为什么不采用这个方案？</strong><select aria-label="拒绝原因" value={rejectionReasonCode ?? ""} onChange={(event) => setRejectionReasonCode((event.target.value || undefined) as PlanRevision["rejectionReasonCode"])}><option value="">请选择原因</option><option value="too_rushed">行程太赶</option><option value="too_much_walking">走路太多</option><option value="activity_mix_not_preferred">活动不符合我的偏好</option><option value="schedule_too_late">结束太晚</option><option value="too_expensive">预算不合适</option><option value="other">其他</option></select><textarea aria-label="补充拒绝原因" placeholder="补充说明（可选）" value={rejectionReasonText} onChange={(event) => setRejectionReasonText(event.target.value)} maxLength={2000} /><button type="button" onClick={() => { setRejecting(false); setRejectionReasonCode(undefined); setRejectionReasonText(""); }}>取消</button><button className="primary" type="button" disabled={busy || !rejectionReasonCode} onClick={() => void rejectWithFeedback()}>确认拒绝</button></div>}</>}{revision.status === "accepted" && <div className="proposal-saved"><p>此记录保留当时应用的内容，最新安排请查看正式行程。</p>{savedPlanError && <p role="alert">方案已保存，但正式行程读取失败：{savedPlanError}。请重试刷新。</p>}<div className="proposal-actions"><button className="primary" type="button" disabled={busy || checking} onClick={() => void viewSavedPlan()}>{busy ? "正在读取正式行程…" : savedPlanError ? "重新加载正式行程" : "查看正式行程"}</button></div></div>}</div>}
        {run?.status === "failed" && <PlanningFailure run={run} disabled={busy || checking || !historyReady} onRetry={() => void start(run.userRequest, run)} onSuggestion={setRequest} />}
        {error && <div className="ai-message agent error" role="alert">{error}{run && <button type="button" disabled={busy} onClick={() => void restore(run)}>重新读取当前方案</button>}</div>}
        <div ref={conversationEnd} />
      </section>
      <footer className="ai-composer">
        {!pending && tripId && <div className="ai-suggestions">
          <button type="button" disabled={busy || checking} onClick={() => setRequest(hasPlan ? `请调整${days.find((day) => day.id === selectedDayId)?.date}的行程，节奏更轻松，减少步行并控制预算。` : "请根据我的旅行日期、预算和偏好生成完整行程。")}>{hasPlan ? <Leaf size={14} aria-hidden="true" /> : <Sparkles size={14} aria-hidden="true" />}{hasPlan ? "当天轻松一点" : "生成完整行程"}</button>
        </div>}
        <div className="ai-composer-shell">
          <textarea onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }} onKeyDown={(event) => sendOnEnter(event, () => void start())} aria-label="告诉旅程总管" placeholder={tripId ? "想了解目的地、旅行体验或目前安排？" : "问问一个城市、聊聊旅行灵感，或说说你在意的体验…"} value={request} onChange={(event) => setRequest(event.target.value)} maxLength={4000} rows={3} disabled={inputBlocked || busy || checking} />
          <div className="ai-composer-actions"><span><ShieldCheck size={14} aria-hidden="true" />仅在你确认后更新正式行程</span><button className="ai-send" type="button" disabled={inputBlocked || busy || checking || !historyReady || !request.trim()} onClick={() => void start()}>{busy || checking || inputBlocked ? <LoaderCircle size={16} className="ai-send-spinner" aria-hidden="true" /> : <ArrowUp size={17} aria-hidden="true" />}{busy || checking ? "正在处理…" : inputBlocked ? "正在处理你的需求…" : "发送需求"}</button></div>
        </div>
        <small>{historyReady ? <><kbd>Enter</kbd> 发送<span className="ai-shortcut-divider">·</span><kbd>Shift + Enter</kbd> 换行</> : "正在打开对话…"}</small>
      </footer>
    </aside>
  </div>;
}

function statusText(status: PlanningRun["status"]) {
  return ({ queued: "任务已进入队列…", researching: "正在检索目的地特色、热门景点与旅行事宜…", planning: "正在生成候选行程…", validating: "正在校验路线、时间与预算…", answered: "已回答", awaiting_clarification: "待补充", awaiting_confirmation: "待确认", accepted: "已应用", rejected: "未采用", failed: "失败", cancelled: "已取消" } as Record<string, string>)[status] ?? "正在处理…";
}

function rejectionReasonLabel(code?: string): string {
  return ({ too_rushed: "行程太赶", too_much_walking: "走路太多", activity_mix_not_preferred: "活动不符合偏好", schedule_too_late: "结束太晚", too_expensive: "预算不合适", other: "其他反馈" } as Record<string, string>)[code ?? ""] ?? "已记录的上次反馈";
}

function factStatus(status?: string) { return status === "available" ? "已获取" : status === "unavailable" ? "暂不可用" : "未配置"; }
function moneyImpact(summary: Record<string, unknown>) { const value = summary["budget_delta_fen"] ?? summary["planned_budget_delta_fen"]; return typeof value === "number" ? `${value >= 0 ? "+" : ""}${formatFen(value)}` : "待确认"; }
function validationText(result: Record<string, unknown>) { return result["valid"] === false || result["status"] === "failed" ? "需处理" : result["valid"] === true || result["status"] === "passed" ? "通过" : "已完成检查"; }

function messageOf(cause: unknown) {
  return planningErrorMessage(cause instanceof Error ? cause.message : "AI 服务暂时不可用");
}

function AnswerText({ text }: { text: string }) {
  return <span>{text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => part.startsWith("**") && part.endsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> : part)}</span>;
}
