import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { Draft } from "../data/draftRepository";
import { DraftPromotionRepository, type PreparedPlan, type PromotionOperation } from "../data/draftPromotionRepository";
import { errorMessage } from "./journeyApi";
import { readScene, useJourneyScene, writeScene } from "./continuity";

const api = new DraftPromotionRepository();
const labels: Record<PromotionOperation["status"], string> = { requested: "已确认，正在准备旅行", trip_created: "旅行已创建，等待采用日程", awaiting_apply: "旅行已创建，日程待采用", needs_review: "情况有变化，需要重新核对", applied: "旅行和日程已确认", created: "旅行已创建，日程尚未采用", failed: "处理未完成，可以恢复", cancelled: "本次授权已撤回" };
const money = (amount: number | null) => amount == null ? "未设上限" : `¥${(amount / 100).toFixed(2)}`;
export function JourneyPromotion({ draft, disabled }: { draft: Draft; disabled: boolean }) {
  const [form, setForm] = useJourneyScene(`draft.${draft.id}.dates`, { start: "", total: "", daily: "", mode: "walk", duration: 90, estimate: 100 });
  const [prepared, setPrepared] = useJourneyScene<PreparedPlan | null>(`draft.${draft.id}.prepared`, null);
  const [reviewId, setReviewId] = useJourneyScene<string | undefined>(`draft.${draft.id}.review`, undefined);
  const [confirmation, setConfirmation] = useJourneyScene<{ preparedId: string; action: "create_only" | "create_and_adopt"; requestId: string } | null>(`draft.${draft.id}.confirmation`, null);
  const [operations, setOperations] = useState<PromotionOperation[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function load() { try { const next = await api.list(draft.id); setOperations(next); if (prepared && next.some(operation => operation.prepared_id === prepared.id)) { setPrepared(null); setConfirmation(null); } } catch (e) { setError(errorMessage(e)); } }
  useEffect(() => { void load(); }, [draft.id]);
  useEffect(() => { if (!operations.some(o => ["requested", "trip_created", "awaiting_apply"].includes(o.status))) return; const timer = setInterval(() => void load(), 3000); return () => clearInterval(timer); }, [operations]);
  async function preview(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setPrepared(null);
    try { setPrepared(await api.preview(draft.id, { expected_version: draft.version, start_date: form.start, total_budget_fen: form.total ? Math.round(Number(form.total) * 100) : null, daily_budget_fen: form.daily ? Math.round(Number(form.daily) * 100) : null, transport_mode: form.mode as "walk" | "driving", duration_minutes: form.duration, unknown_cost_estimate_fen: Math.round(form.estimate * 100), operation_id: reviewId })); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function confirm(action: "create_only" | "create_and_adopt") {
    if (!prepared || (confirmation?.preparedId === prepared.id && confirmation.action !== action)) return; setBusy(true); setError("");
    const key = `promotion.${draft.id}.${prepared.id}`;
    const existing = readScene<{ action: "create_only" | "create_and_adopt"; requestId: string } | null>(key, null);
    if (existing && existing.action !== action) { setError("这份方案已提交另一项确认，请读取原操作状态。不要重复创建旅行。"); setBusy(false); return; }
    const requestId = existing?.requestId || crypto.randomUUID(); writeScene(key, { action, requestId });
    setConfirmation({ preparedId: prepared.id, action, requestId });
    try {
      const operation = await api.confirm(prepared, action, requestId);
      setOperations(previous => [operation, ...previous.filter(o => o.id !== operation.id)]);
      setPrepared(null); setReviewId(undefined); setConfirmation(null);
      const updated = await api.resume(operation.id);
      setOperations(previous => [updated, ...previous.filter(o => o.id !== updated.id)]);
    } catch (e) { setError(errorMessage(e)); await load(); } finally { setBusy(false); }
  }
  async function act(operation: PromotionOperation, action: "resume" | "cancel") {
    setBusy(true); setError("");
    try { const result = await api[action](operation.id); setOperations(previous => [result, ...previous.filter(o => o.id !== result.id)]); }
    catch (e) { setError(errorMessage(e)); await load(); } finally { setBusy(false); }
  }
  const uncertain = !!prepared && confirmation?.preparedId === prepared.id;
  const stale = !!prepared && (prepared.draft_version !== draft.version || Date.parse(prepared.expires_at) <= Date.now());
  return <section className="journeys-card journeys-promotion" aria-label="准备正式旅行"><span className="journeys-eyebrow">WHEN YOU ARE READY</span><h2>日期确定了，再确认正式安排</h2><p>先把活动放到真实日期，核对地点、时间、路线和费用。准备方案不会创建旅行。</p>
    <form onSubmit={preview} onChange={() => setPrepared(null)}><fieldset disabled={busy || uncertain}><div className="journeys-form-grid"><label>出发日期<input type="date" required value={form.start} onChange={e => setForm({ ...form, start: e.target.value })} /></label><label>总预算（元，可留空）<input type="number" min="0.01" step="0.01" value={form.total} onChange={e => setForm({ ...form, total: e.target.value })} /></label><label>每日预算（元，可留空）<input type="number" min="0.01" step="0.01" value={form.daily} onChange={e => setForm({ ...form, daily: e.target.value })} /></label><label>交通方式<select value={form.mode} onChange={e => setForm({ ...form, mode: e.target.value })}><option value="walk">步行</option><option value="driving">驾车</option></select></label><label>每处活动停留（分钟）<input type="number" required min={15} max={480} value={form.duration} onChange={e => setForm({ ...form, duration: Number(e.target.value) })} /></label><label>未知费用暂按（元/地点）<input type="number" required min="0.01" step="0.01" value={form.estimate} onChange={e => setForm({ ...form, estimate: Number(e.target.value) })} /></label></div><p className="journeys-muted">费用为供应商参考或你的规划估算，不能用于预订。正式日程仍需检查营业、门票和预约。</p>{reviewId && <p>将为已创建的同一次旅行重新准备方案。</p>}<button className="journeys-primary" disabled={busy || disabled || uncertain || !draft.plan}>查看日期和完整方案</button>{disabled && <p className="journeys-muted">请先完成并保存草稿修改。</p>}</fieldset></form>
    {error && <p role="alert" className="journeys-notice">{error}</p>}{busy && <p role="status">正在处理。若离开页面，回来后可读取同一次操作的状态。</p>}
    {uncertain && <p className="journeys-notice">这份方案已经提交确认。若响应中断，请重试相同确认或<button disabled={busy} onClick={() => void load()}>读取原操作状态</button>，不要再次创建另一份旅行。</p>}{prepared && <article className="journeys-prepared" aria-label="待确认的正式安排"><h3>{prepared.title}</h3><p>{prepared.city} · {prepared.constraints.start_date} — {prepared.end_date}</p><p>总预算{money(prepared.constraints.total_budget_fen)} · 每日预算{money(prepared.constraints.daily_budget_fen)} · {prepared.constraints.transport_mode === "walk" ? "步行" : "驾车"}</p><p>每日09:00–21:00，步行上限60分钟。</p>{prepared.requirements && <p>保留要求：{prepared.requirements}</p>}
    {Array.from(new Set(prepared.activities.map(a => a.day_date))).map(date => <section key={date}><h4>{date}</h4><ol className="journeys-activities">{prepared.activities.filter(a => a.day_date === date).map(a => <li key={a.ref}><strong>{a.planned_start_time.slice(0, 5)} {a.name}</strong><p>停留{a.duration_minutes}分钟 · {a.cost_nature === "provider_reference" ? "供应商参考" : "规划估算"} {money(a.estimated_cost_fen)}</p>{a.note && <p>{a.note}</p>}{!a.place_id && <p>地点尚待确认</p>}</li>)}</ol></section>)}
    {prepared.routes.map((r, index) => <p key={index}>{prepared.activities.find(a => a.ref === r.from_ref)?.name} → {prepared.activities.find(a => a.ref === r.to_ref)?.name} · {Math.ceil(r.route.duration_seconds / 60)}分钟 · {(r.route.distance_meters / 1000).toFixed(1)}公里</p>)}<p>列出活动费用合计：{money(prepared.activities.reduce((sum, a) => sum + a.estimated_cost_fen, 0))}</p>
    <div className="journeys-diff-columns"><div><h4>已检查</h4><ul>{prepared.coverage.checked.map(s => <li key={s}>{s.replace("正式Validator将在已授权创建Trip后再次校验", "正式采用时会再次检查整份日程的可行性")}</li>)}</ul></div><div><h4>仍需核实</h4><ul>{prepared.coverage.missing.map(s => <li key={s}>{s.replace("正式Validator将在已授权创建Trip后再次校验", "正式采用时会再次检查整份日程的可行性")}</li>)}</ul></div></div>{prepared.coverage.blockers.length > 0 && <div className="journeys-notice"><h4>采用前需要解决</h4><ul>{prepared.coverage.blockers.map(s => <li key={s}>{s.replace("正式Validator将在已授权创建Trip后再次校验", "正式采用时会再次检查整份日程的可行性")}</li>)}</ul></div>}
    <p>确认只授权上面显示的方案。草稿版本或已核实事实变化时，会停止采用并要求重新核对。</p>{stale && <p role="alert">草稿或有效期已变化，请重新准备方案。</p>}<div className="journeys-actions"><button className="journeys-primary" disabled={busy || disabled || stale || (uncertain && confirmation.action !== "create_and_adopt") || prepared.coverage.blockers.length > 0} onClick={() => void confirm("create_and_adopt")}>确认创建并采用这份日程</button><button disabled={busy || disabled || stale || (uncertain && confirmation.action !== "create_only")} onClick={() => void confirm("create_only")}>只创建旅行，日程稍后确认</button><button disabled={busy || uncertain} onClick={() => setPrepared(null)}>返回修改草稿</button></div></article>}
    {operations.length > 0 && <div className="journeys-promotion-records"><h3>本草稿的确认进度</h3><button disabled={busy} onClick={() => void load()}>刷新确认状态</button>{operations.map(operation => <article key={operation.id}><h4>{labels[operation.status]}</h4>{operation.error && <p role="alert">{operation.error}</p>}{operation.validation?.errors.map(e => <p key={e.code}>{e.message}</p>)}{operation.target_trip_id && <p><Link to={`/trips/${operation.target_trip_id}`}>查看这次旅行 →</Link>{operation.status !== "applied" && " · 日程尚未采用。"}</p>}<div className="journeys-actions">{["requested", "trip_created", "awaiting_apply", "failed"].includes(operation.status) && <button disabled={busy} onClick={() => void act(operation, "resume")}>恢复本次处理</button>}{["needs_review", "failed"].includes(operation.status) && <button disabled={busy} onClick={() => { setReviewId(operation.id); setPrepared(null); }}>重新准备并核对方案</button>}{!["applied", "created", "cancelled"].includes(operation.status) && <button disabled={busy} onClick={() => void act(operation, "cancel")}>撤回本次采用授权</button>}</div></article>)}</div>}
  </section>;
}


