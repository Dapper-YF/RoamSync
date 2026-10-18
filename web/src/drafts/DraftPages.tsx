import { useEffect, useState, type FormEvent } from "react";
import { Link, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { DraftRepository, type Draft } from "../data/draftRepository";
import "./drafts.css";
import { DraftPromotionPanel } from "./DraftPromotionPanel";

const repository = new DraftRepository();

export function DraftPages() {
  return <div className="draft-pages"><Routes><Route index element={<DraftList />} /><Route path=":draftId" element={<DraftEditor />} /></Routes></div>;
}

export function DraftList() {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [city, setCity] = useState("杭州");
  const [requirements, setRequirements] = useState("");
  const [days, setDays] = useState(3);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const load = () => repository.list().then(setDrafts).catch(e => setError(String(e.message)));
  useEffect(() => { void load(); }, []);
  async function create(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { const draft = await repository.create({ city, day_count: days, requirements, title: `${city}${days}日自由草稿` }); navigate(`/drafts/${draft.id}`); }
    catch (e) { setError(e instanceof Error ? e.message : "创建失败，请重试。"); }
    finally { setBusy(false); }
  }
  return <main><Link to="/">← 返回探索</Link><h1>先想好怎么玩，日期以后再定</h1><p>自由草稿独立保存，不会创建或修改正式旅程。</p>
    <form onSubmit={create}><label>目的地<input required maxLength={100} value={city} onChange={e => setCity(e.target.value)} /></label>
      <label>旅行天数<input type="number" min={1} max={14} value={days} onChange={e => setDays(Number(e.target.value))} /></label>
      <label>想怎么玩<textarea maxLength={3000} value={requirements} onChange={e => setRequirements(e.target.value)} placeholder="例如：三天慢慢逛，喜欢自然和本地小吃" /></label>
      <button disabled={busy}>{busy ? "创建中…" : "创建未定日期草稿"}</button></form>
    {error && <p role="alert">{error}<button onClick={() => { setError(""); void load(); }}>重新加载</button></p>}
    <h2>我的草稿</h2>{drafts.length === 0 && <p>还没有草稿，先记下旅行想法吧。</p>}
    {drafts.map(d => <article key={d.id}><Link to={`/drafts/${d.id}`}>{d.title}</Link><p>{d.city} · {d.day_count}天 · {d.status === "cancelled" ? "已取消，可恢复" : d.saved ? "已保存" : "编辑中"}</p></article>)}
  </main>;
}

export function DraftEditor() {
  const { draftId = "" } = useParams();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [requirements, setRequirements] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = () => repository.get(draftId).then(result => setDraft(previous =>
    !previous || result.id !== previous.id || result.version >= previous.version ? result : previous)).catch(e => setError(String(e.message)));
  useEffect(() => { setDraft(null); void load(); }, [draftId]);
  useEffect(() => {
    if (!busy && !draft?.runs.some(run => run.status === "running")) return;
    const timer = setInterval(() => { void load(); }, 1500);
    return () => clearInterval(timer);
  }, [busy, draftId, draft?.runs.some(run => run.status === "running")]);
  async function perform(action: "generate" | "save" | "cancel" | "restore" | "cancel-run") {
    if (!draft) return; setError("");
    if (action === "generate") setBusy(true);
    try {
      const result = await (action === "generate" ? repository.run(draft, requirements) : repository.action(draft, action));
      setDraft(previous => !previous || result.version >= previous.version ? result : previous);
      if (action === "cancel-run" || action === "cancel") setBusy(false);
    }
    catch (e) { setError(e instanceof Error ? e.message : "操作失败，请重试。"); await load(); }
    finally { if (action === "generate") setBusy(false); }
  }
  const running = busy || draft?.runs.some(run => run.status === "running");
  return <main><Link to="/drafts">← 我的草稿</Link>{error && <p role="alert">{error}<button onClick={() => void load()}>刷新重试</button></p>}
    {!draft ? <p>正在读取草稿…</p> : <><h1>{draft.title}</h1><p>{draft.city} · {draft.day_count}天 · 日期未定 · {draft.saved ? "已保存" : "更改自动保留，可保存当前版本"}</p>
      {draft.status === "cancelled" ? <><p>草稿已取消，内容仍保留。</p><button onClick={() => void perform("restore")}>恢复草稿</button></> : <>
        <label>修改要求<textarea maxLength={3000} value={requirements} onChange={e => setRequirements(e.target.value)} placeholder="例如：第二天轻松一点，增加湖边散步" /></label>
        <div className="draft-actions"><button disabled={!!running} onClick={() => void perform("generate")}>{running ? "正在构思…" : draft.plan ? "按要求修改草稿" : "生成旅行草稿"}</button>
          <button disabled={!draft.plan || !!running} onClick={() => void perform("save")}>保存草稿</button>
          {running && <button onClick={() => void perform("cancel-run")}>取消本次生成</button>}
          <button onClick={() => void perform("cancel")}>取消草稿</button></div></>}
      <p>这是待核实的活动建议，不是预订或可行性承诺。仅对服务端确认的真实地点提供详情；不提供实时房价和库存，出发前请核实营业安排。</p>
      {draft.plan?.days.map(day => <section key={day.day_index}><h2>第{day.day_index}天 · {day.title}</h2>{day.items.map((item, index) => <article key={index}>
        {item.place_id && item.identity_status === "provider_confirmed" ? <Link to={`/places/${item.place_id}`}>{item.name}</Link> : <strong>{item.name} · 地点待确认</strong>}<p>{item.note}</p></article>)}</section>)}
      <details><summary>生成和修改记录</summary>{[...draft.runs].reverse().map(run => <p key={run.id}>{run.source === "model" ? "模型生成" : "演示数据"} · {({ running: "进行中", completed: "已完成", failed: "失败，可重试", cancelled: "已取消", interrupted: "已中断，可重新生成" })[run.status]} · {run.requirements || "初次规划"}{run.error && `：${run.error}`}</p>)}</details>
      <DraftPromotionPanel draft={draft} disabled={!!running} />
    </>}</main>;
}
