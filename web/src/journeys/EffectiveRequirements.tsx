import { useEffect, useState } from "react";

type Requirement = { id: string; text: string; strength: "hard" | "soft"; status: "active" | "revoked" | "superseded"; source: { kind: string; ref: string }; scope: { kind: string; day_index?: number | null; date?: string | null }; supersedes: string[] };
type RequirementsState = { version: number; records: Requirement[]; effective_by_day?: Record<string, Requirement[]>; effective_by_date?: Record<string, Requirement[]> };

function checkedState(value: unknown): RequirementsState {
  if (!value || typeof value !== "object" || !("records" in value) || !Array.isArray(value.records)
      || !("version" in value) || !Number.isInteger(value.version)
      || value.records.some(record => !record || typeof record.id !== "string" || typeof record.text !== "string"
        || !record.scope || !["active", "revoked", "superseded"].includes(record.status))) {
    throw new Error("要求返回内容暂时不可用，请刷新后重试。");
  }
  return value as RequirementsState;
}

/** Small shared control; requirement changes never accept or edit an itinerary. */
export function EffectiveRequirements({ kind, id, version, disabled = false, onChanged }: {
  kind: "draft" | "trip"; id: string; version?: number; disabled?: boolean; onChanged?: () => void;
}) {
  const [state, setState] = useState<RequirementsState | null>(null);
  const [scope, setScope] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const base = `/api/v1/${kind === "draft" ? "drafts" : "trips"}/${encodeURIComponent(id)}/requirements`;
  useEffect(() => {
    let disposed = false;
    fetch(base).then(async response => { if (!response.ok) throw new Error("要求暂时无法读取"); return checkedState(await response.json()); })
      .then(value => { if (!disposed) { setState(value); setError(""); } })
      .catch(() => { if (!disposed) setError("要求暂时无法读取，请刷新后重试。"); });
    return () => { disposed = true; };
  }, [base, version]);
  const byDay = state?.effective_by_day ?? state?.effective_by_date ?? {};
  async function revoke(record: Requirement) {
    if (!state) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`${base}/revoke`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        expected_version: state.version, requirement_id: record.id,
        ...(scope ? kind === "draft" ? { day_index: Number(scope) } : { day_date: scope } : {}),
      }) });
      if (!response.ok) throw new Error("要求已经更新或当前操作不可用，请刷新后重试。");
      const refreshed = await fetch(base);
      if (!refreshed.ok) throw new Error("要求已撤销，请刷新查看最新状态。");
      setState(checkedState(await refreshed.json())); onChanged?.();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "撤销失败，请重试。"); }
    finally { setBusy(false); }
  }
  return <section className="journeys-card" aria-label="有效要求"><h2>有效要求</h2>
    {error && <p role="alert">{error}</p>}
    <details><summary>查看或撤销已保存要求{state ? `（${state.records.filter(record => record.status === "active").length}条）` : ""}</summary>
    <p className="journeys-muted">来自你的明确表达。建议、收藏与活动锁定各有独立作用。</p>
    {state && <><label>撤销范围<select aria-label="要求撤销范围" value={scope} disabled={disabled || busy} onChange={event => setScope(event.target.value)}>
      <option value="">该要求的全部适用范围</option>{Object.keys(byDay).map(day => <option key={day} value={day}>{kind === "draft" ? `仅第${day}天` : `仅${day}`}</option>)}
    </select></label>
    {!state.records.some(record => record.status === "active") && <p>还没有单独记录的有效要求。</p>}
    <ul>{state.records.filter(record => record.status === "active").map(record => {
      const dates = Object.entries(byDay).filter(([, records]) => records.some(item => item.id === record.id)).map(([day]) => kind === "draft" ? `第${day}天` : day);
      return <li key={record.id}><p>{record.text} <small>{record.strength === "hard" ? "明确硬要求，候选仍需核验" : "尽量满足"}</small></p>
        <p className="journeys-muted">适用：{dates.join("、") || record.scope.date || "当前范围"} · 来源：用户明确要求</p>
        <button disabled={disabled || busy || (!!scope && !(byDay[scope] ?? []).some(item => item.id === record.id))} onClick={() => void revoke(record)}>撤销这条要求</button></li>;
    })}</ul>
    {state.records.some(record => record.status !== "active") && <details><summary>查看已撤销或被覆盖的要求</summary><ul>{state.records.filter(record => record.status !== "active").map(record => <li key={record.id}>{record.text}（{record.status === "revoked" ? "已撤销" : "已被覆盖"}）</li>)}</ul></details>}</>}
    </details>
  </section>;
}
