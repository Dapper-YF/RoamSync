import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, CalendarDays, Compass, FilePenLine, MapPin } from "lucide-react";
import { ApiTripPlanningRepository } from "../data/apiTripPlanningRepository";
import type { Draft } from "../data/draftRepository";
import type { Trip } from "../domain/types";
import { errorMessage, journeyDrafts, localDate, tripPhase } from "./journeyApi";
import { useJourneyScene } from "./continuity";
import "./journeys.css";

const tripsRepository = new ApiTripPlanningRepository();
const groups = [["drafts", "正在筹划", "日期可以以后再定。先把想去的地方和旅行要求安排好。"], ["upcoming", "即将出发", "查看已经确认的安排，核对出发前需要的信息。"], ["active", "正在旅行", "继续当前活动，查看下一站和实际进度。"], ["history", "历史旅行", "回看过去保留的日程。"]] as const;
export function JourneysPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [trips, setTrips] = useState<Trip[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [tab, setTab] = useJourneyScene<string>("tab", "drafts");
  const [create, setCreate] = useJourneyScene("create", { city: "", title: "", requirements: "", days: 3 });
  const [busy, setBusy] = useState(false);
  const [browse, setBrowse] = useJourneyScene("browse", { query: "", limit: 12 });
  const isNew = location.pathname === "/drafts/new";
  async function load() {
    setLoading(true); setError("");
    const results = await Promise.allSettled([journeyDrafts.list(), tripsRepository.listTrips()]);
    if (results[0].status === "fulfilled") setDrafts(results[0].value);
    if (results[1].status === "fulfilled") setTrips(results[1].value);
    const failures = results.filter(r => r.status === "rejected");
    if (failures.length) setError(failures.map(r => r.status === "rejected" ? errorMessage(r.reason) : "").join(" "));
    setLoading(false);
  }
  useEffect(() => { void load(); }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { const draft = await journeyDrafts.create({ city: create.city.trim(), title: create.title.trim() || `${create.city.trim()}旅行想法`, day_count: create.days, requirements: create.requirements }); navigate(`/drafts/${draft.id}`); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  const today = localDate();
  const chosen = groups.find(g => g[0] === tab) || groups[0];
  const match = (text: string) => text.toLocaleLowerCase().includes(browse.query.trim().toLocaleLowerCase());
  const shownTrips = trips.filter(t => tripPhase(t, today) === tab && match(`${t.title} ${t.destination} ${t.startDate} ${t.endDate}`));
  const shownDrafts = drafts.filter(d => match(`${d.title} ${d.city} ${d.requirements}`));
  return <main className="journeys-page"><div className="journeys-heading"><div><span className="journeys-eyebrow">YOUR NEXT CHAPTER</span><h1>{isNew ? "从一个旅行想法开始" : "旅程，按你的节奏继续"}</h1><p>{isNew ? "不必先确定日期，留下目的地和想怎么玩。" : "想法、已经确认的安排，以及正在发生的旅行。"}</p></div>{!isNew && <Link className="journeys-primary" to="/drafts/new"><FilePenLine size={17} />筹划新旅行</Link>}</div>
    {error && <div role="alert" className="journeys-notice">{error}<button onClick={() => void load()}>重新读取</button></div>}
    {isNew ? <><Link className="journeys-back" to="/trips">← 返回旅程</Link><form className="journeys-card journeys-create" onSubmit={submit}><label>想去哪里<input required maxLength={100} placeholder="输入城市或目的地" value={create.city} onChange={e => setCreate({ ...create, city: e.target.value })} /></label><label>为这次旅行起个名字<input maxLength={200} placeholder="可留空" value={create.title} onChange={e => setCreate({ ...create, title: e.target.value })} /></label><label>玩几天<input required type="number" min={1} max={14} value={create.days} onChange={e => setCreate({ ...create, days: Number(e.target.value) })} /></label><label>你想怎样度过这几天<textarea maxLength={3000} placeholder="同行人、节奏、特别想去的地方，或需要避免的安排" value={create.requirements} onChange={e => setCreate({ ...create, requirements: e.target.value })} /></label><button className="journeys-primary" disabled={busy}>{busy ? "正在创建…" : "开始筹划"}<ArrowRight size={17} /></button></form></> : <>
    <div className="journeys-tabs" role="tablist" aria-label="旅程阶段">{groups.map(([key, label]) => <button role="tab" aria-selected={tab === key} className={tab === key ? "selected" : ""} key={key} onClick={() => setTab(key)}>{label}<span>{key === "drafts" ? drafts.length : trips.filter(t => tripPhase(t, today) === key).length}</span></button>)}</div>
    <label className="journeys-list-search">查找我的旅程<input placeholder="旅行名称、目的地或日期" value={browse.query} onChange={e => setBrowse({ query: e.target.value, limit: 12 })} /></label><section aria-label={chosen[1]}><h2>{chosen[1]}</h2><p className="journeys-muted">{chosen[2]}</p>{loading ? <p role="status">正在读取你的旅程…</p> : tab === "drafts" ? <div className="journeys-grid">{shownDrafts.slice(0, browse.limit).map(d => <Link className="journeys-card journeys-trip-card" key={d.id} to={`/drafts/${d.id}`}><FilePenLine /><span className="journeys-chip">{d.status === "cancelled" ? "已暂停，可恢复" : d.saved ? "已保存草稿" : "继续筹划"}</span><h3>{d.title}</h3><p><MapPin size={14} />{d.city} · {d.day_count}天 · 日期未定</p><p>{d.requirements || "打开草稿，继续安排想去的地方。"}</p><strong>{d.status === "cancelled" ? "查看和恢复" : "继续编辑"}<ArrowRight size={16} /></strong></Link>)}{shownDrafts.length === 0 && !error && <Empty label="还没有旅行草稿" detail="如果只是想找个地方逛逛，可以直接探索；想筹划几天的旅行，再从这里开始。" />}</div> : <div className="journeys-grid">{shownTrips.slice(0, browse.limit).map(t => <Link className="journeys-card journeys-trip-card" key={t.id} to={`/trips/${t.id}`}><CalendarDays /><span className="journeys-chip">{chosen[1]}</span><h3>{t.title}</h3><p><MapPin size={14} />{t.destination}</p><p>{t.startDate} — {t.endDate}</p><strong>{tab === "active" ? "继续今天的旅行" : tab === "history" ? "回看日程" : "查看出发安排"}<ArrowRight size={16} /></strong></Link>)}{shownTrips.length === 0 && !error && <Empty label={`暂无${chosen[1]}`} detail="你保留的正式安排会显示在对应阶段。" />}</div>}{(tab === "drafts" ? shownDrafts.length : shownTrips.length) > browse.limit && <button className="journeys-secondary" onClick={() => setBrowse({ ...browse, limit: browse.limit + 12 })}>查看更多旅程（已显示{browse.limit}条）</button>}</section></>}
  </main>;
}
function Empty({ label, detail }: { label: string; detail: string }) { return <div className="journeys-empty"><Compass size={30} /><h3>{label}</h3><p>{detail}</p><Link to="/">去探索目的地</Link></div>; }

