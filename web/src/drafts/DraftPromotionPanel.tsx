import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import type { Draft } from "../data/draftRepository";
import { DraftPromotionRepository, type PreparedPlan, type PromotionOperation } from "../data/draftPromotionRepository";

const repository = new DraftPromotionRepository();
const labels = { requested: "已授权，等待创建", trip_created: "旅行已创建，方案尚未采用", awaiting_apply: "旅行已创建，候选等待复核采用",
  needs_review: "需要重新检查并确认", applied: "旅行已创建，当前方案已采用", created: "旅行已创建，未自动采用方案", failed: "处理失败，可恢复当前操作", cancelled: "授权已撤回" };
const money = (fen: number) => `¥${(fen / 100).toFixed(2)}`;

export function DraftPromotionPanel({ draft, disabled = false }: { draft: Draft; disabled?: boolean }) {
  const [start, setStart] = useState("");
  const [total, setTotal] = useState("");
  const [daily, setDaily] = useState("");
  const [mode, setMode] = useState<"walk" | "driving">("walk");
  const [duration, setDuration] = useState(90);
  const [estimate, setEstimate] = useState(100);
  const [prepared, setPrepared] = useState<PreparedPlan | null>(null);
  const [operations, setOperations] = useState<PromotionOperation[]>([]);
  const [reviewId, setReviewId] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = async () => { const result = await repository.list(draft.id); setOperations(Array.isArray(result) ? result : []); };
  useEffect(() => { setPrepared(null); setReviewId(undefined); void load().catch(() => {}); }, [draft.id, draft.version]);
  const update = (operation: PromotionOperation) => setOperations(previous => [operation, ...previous.filter(op => op.id !== operation.id)]);
  async function preview(event: FormEvent) {
    event.preventDefault(); setPrepared(null); setError("");
    const parsed = Date.parse(`${start}T00:00:00Z`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !Number.isFinite(parsed) || new Date(parsed).toISOString().slice(0, 10) !== start) {
      setError("请按YYYY-MM-DD填写有效的出发日期，例如2026-11-01。"); return;
    }
    setBusy(true);
    try { setPrepared(await repository.preview(draft.id, { expected_version: draft.version, start_date: start,
      total_budget_fen: total ? Math.round(Number(total) * 100) : null, daily_budget_fen: daily ? Math.round(Number(daily) * 100) : null,
      transport_mode: mode, duration_minutes: duration, unknown_cost_estimate_fen: Math.round(estimate * 100), operation_id: reviewId })); }
    catch (e) { setError(e instanceof Error ? e.message : "准备失败，请重试。"); }
    finally { setBusy(false); }
  }
  async function confirm(action: "create_only" | "create_and_adopt") {
    if (!prepared) return;
    setBusy(true); setError("");
    // Same prepared/action retains the same key after a lost HTTP response and refresh.
    const key = `draft-promotion:${draft.id}:${prepared.id}:${action}`;
    const requestId = sessionStorage.getItem(key) ?? crypto.randomUUID();
    sessionStorage.setItem(key, requestId);
    try {
      const operation = await repository.confirm(prepared, action, requestId);
      update(operation);
      setPrepared(null);
      update(await repository.resume(operation.id));
    } catch (e) { setError(e instanceof Error ? e.message : "操作中断，请刷新当前转换状态后重试。"); await load().catch(() => {}); }
    finally { setBusy(false); }
  }
  async function act(operation: PromotionOperation, action: "resume" | "cancel") {
    if (action === "resume") setBusy(true);
    setError("");
    try { update(await repository[action](operation.id)); }
    catch (e) { setError(e instanceof Error ? e.message : "状态读取失败，请刷新。"); }
    finally { if (action === "resume") setBusy(false); }
  }
  const stale = prepared && (prepared.draft_version !== draft.version || Date.parse(prepared.expires_at) <= Date.now());
  return <section aria-label="将草稿变成正式旅行"><h2>日期确定后，创建旅行</h2>
    <p>先查看绑定真实日期的完整方案。准备方案不会创建旅行。确认后若处理中断，已经创建的旅行会保留，并可从当前操作恢复。</p>
    <form onSubmit={preview} onChange={() => setPrepared(null)}>
      <label>出发日期（YYYY-MM-DD）<input aria-label="出发日期" type="text" inputMode="numeric" placeholder="2026-11-01" required maxLength={10}
        pattern="[0-9]{4}-[0-9]{2}-[0-9]{2}" value={start} onInput={e => setStart(e.currentTarget.value)} onChange={e => setStart(e.target.value)} /></label>
      <label>总预算（元，可留空）<input type="number" min="0.01" step="0.01" value={total} onChange={e => setTotal(e.target.value)} /></label>
      <label>每日预算（元，可留空）<input type="number" min="0.01" step="0.01" value={daily} onChange={e => setDaily(e.target.value)} /></label>
      <label>交通方式<select value={mode} onChange={e => setMode(e.target.value as "walk" | "driving")}><option value="walk">步行</option><option value="driving">驾车</option></select></label>
      <label>每处停留（分钟）<input type="number" min={15} max={480} value={duration} onChange={e => setDuration(Number(e.target.value))} /></label>
      <label>未知费用的规划估算（元/地点）<input type="number" min="0.01" step="0.01" value={estimate} onChange={e => setEstimate(Number(e.target.value))} /></label>
      <p>未知费用使用上面的规划估算；参考价格也不是实时门票或预订报价。预算留空表示不设费用上限。</p>
      {reviewId && <p>正在为原转换准备更新方案，已创建的旅行将复用。</p>}
      <button disabled={busy || disabled || !draft.plan || draft.status !== "active"}>准备日期和完整方案</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {busy && <p role="status">正在处理，请保留页面；如中断，可刷新查看转换记录。</p>}
    {prepared && <article aria-label="待确认的完整方案"><h3>{prepared.city} · {prepared.constraints.start_date} 至 {prepared.end_date}</h3>
      <p>每日09:00–21:00，步行上限60分钟；{prepared.constraints.transport_mode === "walk" ? "步行" : "驾车"}。总预算{prepared.constraints.total_budget_fen == null ? "不限" : money(prepared.constraints.total_budget_fen)}，每日预算{prepared.constraints.daily_budget_fen == null ? "不限" : money(prepared.constraints.daily_budget_fen)}。</p>
      {prepared.requirements && <p>保留的旅行要求：{prepared.requirements}</p>}
      {prepared.activities.map(a => <div key={a.ref}><strong>{a.day_date} {a.planned_start_time.slice(0, 5)} · {a.name}</strong>
        <p>第{a.position + 1}站 · 停留{a.duration_minutes}分钟 · {a.transport_mode === "walk" ? "步行" : "驾车"} · {a.cost_nature === "planning_estimate" ? "规划估算" : "供应商参考价"} {money(a.estimated_cost_fen)}{!a.place_id && " · 地点待确认"}</p><p>{a.note}</p></div>)}
      {prepared.routes.map((r, index) => <p key={index}>路线：{prepared.activities.find(a => a.ref === r.from_ref)?.name} → {prepared.activities.find(a => a.ref === r.to_ref)?.name}，{Math.ceil(r.route.duration_seconds / 60)}分钟 / {(r.route.distance_meters / 1000).toFixed(1)}公里</p>)}
      <p>列出项目合计：{money(prepared.activities.reduce((sum, a) => sum + a.estimated_cost_fen, 0))}</p>
      <h4>已检查</h4><ul>{prepared.coverage.checked.map(s => <li key={s}>{s}</li>)}</ul>
      <h4>仍需核实</h4><ul>{prepared.coverage.missing.map(s => <li key={s}>{s}</li>)}</ul>
      {prepared.coverage.blockers.length > 0 && <><h4>采用前必须解决</h4><ul>{prepared.coverage.blockers.map(s => <li key={s}>{s}</li>)}</ul></>}
      <p>确认仅授权采用上面显示的日期、地点、顺序、时间和费用方案。事实发生变化将停止并要求重新确认。方案有效至{new Date(prepared.expires_at).toLocaleTimeString()}。</p>
      {stale && <p>草稿或方案有效期已变化，请重新准备。</p>}
      <button disabled={busy || !!stale || prepared.coverage.blockers.length > 0} onClick={() => void confirm("create_and_adopt")}>创建并采用当前方案</button>
      <button disabled={busy || !!stale} onClick={() => void confirm("create_only")}>只创建旅行，暂不采用方案</button>
    </article>}
    {operations.length > 0 && <><h3>转换记录</h3><button disabled={busy} onClick={() => void load().catch(e => setError(e.message))}>刷新转换状态</button>
      {operations.map(op => <article key={op.id}><strong>{labels[op.status]}</strong>{op.error && <p>{op.error}</p>}
        {op.target_trip_id && <p><Link to={`/trips/${op.target_trip_id}`}>查看已创建的旅行</Link>{op.status !== "applied" && " · 当前方案未采用，旅行仍保留。"}</p>}
        {op.validation?.errors.map(e => <p key={e.code}>{e.message}</p>)}
        {["requested", "trip_created", "awaiting_apply", "failed"].includes(op.status) && <button disabled={busy} onClick={() => void act(op, "resume")}>恢复当前操作</button>}
        {["needs_review", "failed"].includes(op.status) && <button disabled={busy} onClick={() => { setReviewId(op.id); setPrepared(null); }}>查看新方案并重新确认</button>}
        {!["applied", "created", "cancelled"].includes(op.status) && <button onClick={() => void act(op, "cancel")}>撤回本次采用授权</button>}
      </article>)}</>}
  </section>;
}
