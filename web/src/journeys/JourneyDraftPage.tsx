import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Check, ChevronDown, ChevronUp, MapPin, Plus, Sparkles, Trash2 } from "lucide-react";
import type { Draft, DraftDay } from "../data/draftRepository";
import { errorMessage, journeyDrafts, type JourneyPageProps } from "./journeyApi";
import { readScene, useJourneyScene, writeScene } from "./continuity";
import { JourneyPromotion } from "./JourneyPromotion";
import { DraftPlacePicker } from "./DraftPlacePicker";
import { EffectiveRequirements } from "./EffectiveRequirements";
import "./journeys.css";

type Edit = { baseVersion: number; title: string; requirements: string; plan: Draft["plan"] };
function editOf(draft: Draft): Edit { return { baseVersion: draft.version, title: draft.title, requirements: draft.requirements, plan: structuredClone(draft.plan) }; }
function changed(edit: Edit | null, draft: Draft | null) { return !!edit && !!draft && (edit.title !== draft.title || edit.requirements !== draft.requirements || JSON.stringify(edit.plan) !== JSON.stringify(draft.plan)); }
export function JourneyDraftPage(props: JourneyPageProps) { const { draftId = "" } = useParams(); return <DraftEditor key={draftId} id={draftId} {...props} />; }
function DraftEditor({ id, onAskAssistant }: JourneyPageProps & { id: string }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [edit, setEdit] = useJourneyScene<Edit | null>(`draft.${id}.edit`, null);
  const [proposal, setProposal] = useJourneyScene(`draft.${id}.request`, { scope: "all", text: "" });
  const [before, setBefore] = useJourneyScene<Draft["plan"]>(`draft.${id}.before`, null);
  const [busy, setBusy] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [cancelBusy, setCancelBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reviewSave, setReviewSave] = useState(false);
  const dirty = changed(edit, draft);
  const running = generating || draft?.runs.some(r => r.status === "running") || false;
  const conflict = !!draft && !!edit && dirty && edit.baseVersion !== draft.version;
  async function load() {
    try {
      const next = await journeyDrafts.get(id);
      setDraft(previous => !previous || next.version >= previous.version ? next : previous);
      setEdit(previous => !previous || (draft && previous.baseVersion !== next.version && !changed(previous, draft)) ? editOf(next) : previous);
      if (next.runs.some(r => r.status === "failed" || r.status === "interrupted")) {
        const latest = next.runs[next.runs.length - 1];
        if (latest && ["failed", "interrupted"].includes(latest.status)) setError(latest.error || "本次修改未完成。原草稿仍保留，可以重试。");
      }
    } catch (e) { setError(errorMessage(e)); } finally { setLoading(false); }
  }
  useEffect(() => { void load(); }, [id]);
  useEffect(() => { if (!running) return; const timer = setInterval(() => void load(), 1800); return () => clearInterval(timer); }, [running, draft?.version]);
  async function act(action: "save" | "restore" | "cancel-run") {
    if (!draft) return; if (action === "cancel-run") setCancelBusy(true); else setBusy(true); setError("");
    try { const next = await journeyDrafts.action(draft, action); setDraft(next); if (!dirty) setEdit(editOf(next)); setNotice(action === "restore" ? "草稿已恢复，可以继续编辑。" : action === "cancel-run" ? "已停止本次修改，草稿仍保留。" : "草稿已保存。" ); }
    catch (e) { setError(errorMessage(e)); } finally { if (action === "cancel-run") setCancelBusy(false); else setBusy(false); }
  }
  async function save() {
    if (!draft || !edit || conflict) return; setBusy(true); setError("");
    try {
      setBefore(draft.plan);
      const next = await journeyDrafts.edit(draft, { title: edit.title, requirements: edit.requirements, plan: edit.plan });
      setDraft(next); setEdit(editOf(next)); setReviewSave(false); setNotice("修改已保存，离开后可以继续。" );
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function generate() {
    if (!draft || dirty || !proposal.text.trim()) return; setGenerating(true); setError(""); setNotice("");
    setBefore(draft.plan);
    const key = `draft.${id}.pending-generation`;
    const signature = JSON.stringify([draft.version, proposal]);
    const previous = readScene<{ signature: string; requestId: string } | null>(key, null);
    const requestId = previous?.signature === signature ? previous.requestId : crypto.randomUUID();
    writeScene(key, { signature, requestId });
    try {
      const next = await journeyDrafts.scopedRun(draft, proposal.text, proposal.scope === "all" ? undefined : [Number(proposal.scope)], requestId);
      setDraft(previous => !previous || next.version >= previous.version ? next : previous);
      setEdit(previous => !previous || next.version >= previous.baseVersion ? editOf(next) : previous);
      const result = next.runs.find(run => run.request_id === requestId);
      if (result && result.status !== "running") writeScene(key, null);
      if (result?.status === "failed" || result?.status === "interrupted") setError(result.error || "本次活动建议未完成，原草稿保留。可以换一种要求重试。");
      else if (result?.status === "cancelled") setNotice("本次整理已停止，原草稿保留。");
      else if (result?.status === "completed") setNotice("活动建议已更新，已保留未调整的日期。请核对修改后的内容。");
      else setNotice("正在按你的要求整理。你可以继续浏览，回来后会恢复这份草稿。");
    }
    catch (e) { setError(errorMessage(e)); } finally { setGenerating(false); await load(); }
  }
  function dayChange(index: number, update: (day: DraftDay) => DraftDay) {
    if (!edit?.plan) return;
    setEdit({ ...edit, plan: { days: edit.plan.days.map(day => day.day_index === index ? update(structuredClone(day)) : day) } }); setReviewSave(false);
  }
  if (!draft || !edit) return <main className="journeys-page"><Link to="/trips">← 旅程</Link>{error ? <p role="alert">{error}<button onClick={() => void load()}>重新读取</button></p> : <p role="status">{loading ? "正在读取草稿…" : "草稿暂不可用"}</p>}</main>;
  const disabled = busy || running || draft.status === "cancelled";
  return <main className="journeys-page journeys-draft"><Link className="journeys-back" to="/trips">← 旅程</Link><div className="journeys-heading"><div><span className="journeys-eyebrow">ROOM FOR IDEAS</span><h1>{draft.title}</h1><p>{draft.city} · {draft.day_count}天 · 日期未定 · {dirty ? "有未保存的修改" : draft.saved ? "已保存" : "草稿已保留"}</p></div><button className="journeys-secondary" disabled={!onAskAssistant || dirty} onClick={() => onAskAssistant?.({ city: draft.city, draftContext: { draftId: draft.id, version: draft.version, city: draft.city, requirements: draft.requirements, plan: draft.plan }, prompt: "帮我看看这份草稿，有哪些需要核实的地方？" })}><Sparkles size={17} />和 AI 讨论</button></div>
    {error && <div role="alert" className="journeys-notice">{error}<button onClick={() => { setError(""); void load(); }}>读取最新状态</button></div>}
    {notice && <p role="status" className="journeys-success"><Check size={16} />{notice}</p>}
    {conflict && <div className="journeys-notice">草稿已有更新。你的未保存编辑仍保留；请核对后选择。<button onClick={() => { setEdit(editOf(draft)); setReviewSave(false); }}>放弃本地编辑，使用已保存内容</button></div>}
    {draft.status === "cancelled" && <div className="journeys-notice">这份草稿已暂停，内容仍保留。<button disabled={busy} onClick={() => void act("restore")}>恢复并继续编辑</button></div>}
    <div className="journeys-draft-columns"><section className="journeys-card journeys-requirements"><h2>这次想怎么玩</h2><label>草稿名称<input disabled={disabled} value={edit.title} maxLength={200} onChange={e => setEdit({ ...edit, title: e.target.value })} /></label><label>整段旅行的要求<textarea disabled={disabled} maxLength={3000} value={edit.requirements} onChange={e => setEdit({ ...edit, requirements: e.target.value })} placeholder="节奏、同行人、偏好与需要避免的安排" /></label><p className="journeys-muted">这些要求会保存在草稿里。某一天的调整请在下面选择作用范围。</p><div className="journeys-actions"><button className="journeys-primary" disabled={disabled || conflict || !edit.title.trim()} onClick={() => dirty ? setReviewSave(true) : void act("save")}>{dirty ? "核对并保存修改" : "保存当前草稿"}</button><Link className="journeys-secondary" to="/explore">去探索地点</Link></div>
    <hr /><h3>{draft.plan ? "调整活动建议" : "安排每日活动"}</h3><label>调整范围<select disabled={disabled || !draft.plan} value={proposal.scope} onChange={e => setProposal({ ...proposal, scope: e.target.value })}><option value="all">整段旅行</option>{Array.from({ length: draft.day_count }, (_, i) => <option key={i} value={String(i + 1)}>仅第{i + 1}天</option>)}</select></label><label>{proposal.scope === "all" ? "这次希望怎样安排" : `第${proposal.scope}天怎样调整`}<textarea disabled={disabled} maxLength={3000} value={proposal.text} onChange={e => setProposal({ ...proposal, text: e.target.value })} placeholder="写下这次希望调整的具体要求" /></label>{proposal.scope !== "all" && <p className="journeys-muted">只重新安排第{proposal.scope}天，其余日期由服务端原样保留。</p>}<button className="journeys-primary" disabled={disabled || dirty || !proposal.text.trim()} onClick={() => void generate()}>{running ? "正在整理活动…" : draft.plan ? "按范围调整草稿" : "生成活动建议"}</button>{dirty && <p>先保存你的手动修改，再重新安排。</p>}{running && <button className="journeys-secondary" disabled={cancelBusy || !draft.runs.some(r => r.status === "running")} onClick={() => void act("cancel-run")}>停止本次整理</button>}
    </section><section className="journeys-days" aria-label="每日活动">{!edit.plan && <div className="journeys-empty"><MapPin size={28} /><h2>每天留一点期待</h2><p>写下你想怎样玩，再生成活动建议；日期确定以后再准备正式安排。</p></div>}{edit.plan?.days.map(day => <article className="journeys-card" key={day.day_index}><div className="journeys-day-title"><span>DAY {String(day.day_index).padStart(2, "0")}</span><label>第{day.day_index}天主题<input aria-label={`第${day.day_index}天主题`} disabled={disabled} value={day.title} maxLength={200} onChange={e => dayChange(day.day_index, d => ({ ...d, title: e.target.value }))} /></label></div><ol className="journeys-activities">{day.items.map((item, index) => <li key={index}><div><strong>{item.name}</strong>{item.place_id && item.identity_status === "provider_confirmed" ? <Link to={`/places/${item.place_id}`} state={{ from: `/drafts/${id}` }}>查看地点</Link> : <span className="journeys-muted">地点待核实</span>}</div><label className="journeys-item-note">活动备注<textarea aria-label={`第${day.day_index}天第${index + 1}站备注`} disabled={disabled} maxLength={1000} value={item.note} onChange={e => dayChange(day.day_index, d => { d.items[index].note = e.target.value; return d; })} /></label><DraftPlacePicker city={draft.city} disabled={disabled} initialQuery={item.name} onPick={picked => dayChange(day.day_index, d => { d.items[index] = { ...picked, note: d.items[index].note }; return d; })} /><div className="journeys-item-actions"><button aria-label={`上移${item.name}`} disabled={disabled || index === 0} onClick={() => dayChange(day.day_index, d => { [d.items[index - 1], d.items[index]] = [d.items[index], d.items[index - 1]]; return d; })}><ChevronUp size={15} /></button><button aria-label={`下移${item.name}`} disabled={disabled || index === day.items.length - 1} onClick={() => dayChange(day.day_index, d => { [d.items[index + 1], d.items[index]] = [d.items[index], d.items[index + 1]]; return d; })}><ChevronDown size={15} /></button><button aria-label={`移除${item.name}`} disabled={disabled} onClick={() => dayChange(day.day_index, d => ({ ...d, items: d.items.filter((_, i) => i !== index) }))}><Trash2 size={15} /></button></div></li>)}</ol><DraftPlacePicker city={draft.city} disabled={disabled || day.items.length >= 12} onPick={picked => dayChange(day.day_index, d => ({ ...d, items: [...d.items, picked] }))} /><AddIdea disabled={disabled || day.items.length >= 12} onAdd={name => dayChange(day.day_index, d => ({ ...d, items: [...d.items, { name, note: "", place_id: null, identity_status: "unknown" }] }))} /></article>)}</section></div>
    {reviewSave && <section className="journeys-card" aria-label="保存前核对修改"><h2>核对这次修改</h2>{edit.title !== draft.title && <p>名称：{draft.title} → {edit.title}</p>}{edit.requirements !== draft.requirements && <><p>原要求：{draft.requirements || "未填写"}</p><p>新要求：{edit.requirements || "未填写"}</p></>}<DraftDifference before={draft.plan} after={edit.plan} /><div className="journeys-actions"><button className="journeys-primary" disabled={disabled || conflict} onClick={() => void save()}>确认保存修改</button><button onClick={() => setReviewSave(false)}>继续编辑</button></div></section>}
    {!dirty && before && JSON.stringify(before) !== JSON.stringify(draft.plan) && <details className="journeys-card"><summary>查看最近一次活动调整</summary><DraftDifference before={before} after={draft.plan} /></details>}
    <p className="journeys-muted">活动建议需要核实营业与预约信息。未确认地点不会冒充真实地点；保存草稿不会创建正式旅行。</p>
    <EffectiveRequirements kind="draft" id={draft.id} version={draft.version} disabled={disabled || dirty || conflict} onChanged={() => void load()} />
    <JourneyPromotion draft={draft} disabled={disabled || dirty || conflict} />
  </main>;
}
function AddIdea({ disabled, onAdd }: { disabled: boolean; onAdd: (name: string) => void }) {
  const [name, setName] = useState("");
  return <form className="journeys-add-idea" onSubmit={e => { e.preventDefault(); if (name.trim()) { onAdd(name.trim()); setName(""); } }}><input aria-label="添加活动想法" disabled={disabled} value={name} maxLength={200} placeholder="添加一个待核实的活动想法" onChange={e => setName(e.target.value)} /><button disabled={disabled || !name.trim()} aria-label="添加活动"><Plus size={18} /></button></form>;
}
export function DraftDifference({ before, after }: { before: Draft["plan"]; after: Draft["plan"] }) {
  return <div className="journeys-diff">{after?.days.map(day => { const old = before?.days.find(d => d.day_index === day.day_index); const same = JSON.stringify(old) === JSON.stringify(day); return <article key={day.day_index}><h3>第{day.day_index}天 · {same ? "保持原样" : "有调整"}</h3>{!same && <div className="journeys-diff-columns"><div><h4>修改前</h4><p>{old?.title || "尚未安排"}</p>{old?.items.map((i, n) => <p key={n}>{n + 1}. {i.name}{i.note && ` · ${i.note}`}</p>)}</div><div><h4>修改后</h4><p>{day.title}</p>{day.items.map((i, n) => <p key={n}>{n + 1}. {i.name}{i.note && ` · ${i.note}`}</p>)}</div></div>}</article>; })}</div>;
}



