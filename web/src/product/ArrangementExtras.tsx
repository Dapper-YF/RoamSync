import { useState, type FormEvent } from "react";
import { useTravelAssistant } from "./TravelAssistant";
import { assistantRequest as naturalRequest, choiceLabels as labels, clock, type Choice, type Activity, type PlaceResult } from "./arrangementApi";
import "./NaturalAssistant.css";

// A result editor, not another assistant or a second copy of Trip state.
export function ArrangementExtras() {
  const { arrangement, refreshArrangement: reload, busy: assistantBusy } = useTravelAssistant();
  const tripId = arrangement?.trip.id;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [route, setRoute] = useState<{ day: string; legs: { duration_minutes: number; provider: string; is_estimated: boolean }[] }>();
  const [newLabel, setNewLabel] = useState("");
  const [newKind, setNewKind] = useState("selected");
  const [editing, setEditing] = useState<Activity>();
  const [editTime, setEditTime] = useState("");
  const [editDuration, setEditDuration] = useState(60);
  const [scheduling, setScheduling] = useState<Choice>();
  const [placeQuery, setPlaceQuery] = useState("");
  const [placeResults, setPlaceResults] = useState<PlaceResult[]>([]);
  const [selectedPlace, setSelectedPlace] = useState<PlaceResult>();
  const [scheduleDay, setScheduleDay] = useState("");
  const [scheduleTime, setScheduleTime] = useState("");
  const [scheduleDuration, setScheduleDuration] = useState("");
  async function task(operation: () => Promise<void>) {
    if (assistantBusy || busy) return;
    setBusy(true); setError(""); setNotice("");
    try { await operation(); } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function changeChoice(item: Choice, kind: string) {
    if (!arrangement) return;
    await task(async () => {
      await naturalRequest(`/trips/${tripId}/arrangement-items/${item.id}`, { method: "PUT", body: JSON.stringify({ expected_version: arrangement.version, kind, label: item.label,
        source_ref: `web:${crypto.randomUUID()}`, place_id: item.place_id, day_date: item.day_date }) });
      await reload(); setNotice("已保存这项决定，其他时间没有重新安排。");
    });
  }
  async function saveActivity(event: FormEvent) {
    event.preventDefault(); if (!editing || !arrangement) return;
    await task(async () => {
      await naturalRequest(`/activities/${editing.id}`, { method: "PUT", headers: { "X-Trip-Version": String(arrangement.version) }, body: JSON.stringify({ version: editing.version, scheduled_time: editTime, duration_minutes: editDuration }) });
      setEditing(undefined); await reload(); setNotice("已保存。已有间隔会保留；只有实际冲突才检查后续安排。");
    });
  }
  async function addChoice(event: FormEvent) {
    event.preventDefault(); if (!newLabel.trim() || !arrangement) return;
    await task(async () => {
      await naturalRequest(`/trips/${tripId}/arrangement-items`, { method: "POST", body: JSON.stringify({ id: crypto.randomUUID(), expected_version: arrangement.version, kind: newKind,
        label: newLabel.trim(), source_ref: `web:${crypto.randomUUID()}` }) });
      setNewLabel(""); await reload();
    });
  }
  async function scheduleChoice(event: FormEvent) {
    event.preventDefault();
    if (!arrangement || !scheduling || !scheduleDay || !scheduleTime || !scheduleDuration || !scheduling.place_id && !selectedPlace) return;
    await task(async () => {
      await naturalRequest(`/trips/${tripId}/arrangement-items/${scheduling.id}/schedule`, { method: "POST", body: JSON.stringify({ expected_version: arrangement.version,
        day_plan_id: scheduleDay, scheduled_time: scheduleTime, duration_minutes: Number(scheduleDuration),
        ...(scheduling.place_id ? { place_id: scheduling.place_id } : { place_snapshot: selectedPlace }) }) });
      setScheduling(undefined); await reload(); setNotice("已按你选择的地点和时间保存，没有补填其他时间；相邻路线仍需核实。");
    });
  }
  if (!arrangement) return null;
  return <section className="arrangement-extras natural-workspace">    <aside className="natural-arrangement" aria-label="我的安排"><div className="natural-panel-heading"><h2>我的安排</h2></div>
      {!arrangement && <div className="natural-empty"><h3>先聊聊，也很好</h3><p>明确日期后，可以请助手整理一份允许留白的建议。你采用后，它才会出现在这里。</p></div>}
      {arrangement && <><h3>{arrangement.trip.title}</h3><p>{arrangement.trip.start_date} — {arrangement.trip.end_date}</p><button onClick={() => void task(reload)} disabled={busy}>刷新已保存内容</button>
        <section aria-label="未排程与备选"><h3>想去的与备选</h3>{arrangement.items.filter(i => !i.activity_id && ["selected", "optional"].includes(i.kind)).map(i => <article className="natural-choice" key={i.id}><strong>{i.label}</strong><span>{labels[i.kind]}{i.day_date ? ` · ${i.day_date}` : ""}</span><small>{i.place_id ? "已关联地点身份；时间尚未确定" : "名称来自讨论，具体地点尚未核实"}</small><div><button disabled={busy} onClick={() => void changeChoice(i, i.kind === "selected" ? "optional" : "selected")}>{i.kind === "selected" ? "改为备选" : "确定纳入"}</button><button disabled={busy} onClick={() => { setScheduling(i); setPlaceQuery(i.label); setPlaceResults([]); setSelectedPlace(undefined); setScheduleDay(""); setScheduleTime(""); setScheduleDuration(""); }}>安排具体时间</button><button disabled={busy} onClick={() => void changeChoice(i, "cancelled")}>取消这项</button></div></article>)}</section>
        {scheduling && <form className="natural-editor" aria-label={`为${scheduling.label}安排具体时间`} onSubmit={scheduleChoice}><h3>给{scheduling.label}安排时间</h3>{!scheduling.place_id && <><label>核对地点<input aria-label="排程地点搜索" value={placeQuery} onChange={e => setPlaceQuery(e.target.value)} /></label><button type="button" disabled={busy || !placeQuery.trim()} onClick={() => void task(async () => { setSelectedPlace(undefined); setPlaceResults(await naturalRequest<PlaceResult[]>(`/trips/${tripId}/places/search?q=${encodeURIComponent(placeQuery)}`)); })}>查询实际地点</button>{placeResults.map(p => <button type="button" key={p.provider_place_id} aria-pressed={selectedPlace?.provider_place_id === p.provider_place_id} onClick={() => setSelectedPlace(p)}>{p.name} · {selectedPlace?.provider_place_id === p.provider_place_id ? "已选择" : "选择此地点"}</button>)}</>}<label>选择日期<select aria-label="排程日期" required value={scheduleDay} onChange={e => setScheduleDay(e.target.value)}><option value="">日期尚未选择</option>{arrangement.days.map(d => <option key={d.id} value={d.id}>{d.date}</option>)}</select></label><label>开始时间<input aria-label="排程开始时间" type="time" required value={scheduleTime} onChange={e => setScheduleTime(e.target.value)} /></label><label>停留分钟<input aria-label="排程停留分钟" type="number" min={5} max={1440} required value={scheduleDuration} onChange={e => setScheduleDuration(e.target.value)} /></label><p>时间和时长由你明确选择，不代表预约或交通已完成核实。</p><button disabled={busy || !scheduling.place_id && !selectedPlace}>保存这项具体安排</button><button type="button" onClick={() => setScheduling(undefined)}>继续保持未定</button></form>}
        <form className="natural-add" onSubmit={addChoice}><label>再记一个地方<input aria-label="事项名称" value={newLabel} onChange={e => setNewLabel(e.target.value)} maxLength={160} /></label><select aria-label="事项选择" value={newKind} onChange={e => setNewKind(e.target.value)}><option value="selected">确定想去，时间未定</option><option value="optional">有时间再去</option></select><button disabled={busy || !newLabel.trim()}>保存这个选择</button></form>
        {arrangement.days.map(d => <section key={d.id}><h3>{d.date}</h3>{d.activities.map(a => <button key={a.id} disabled={busy} onClick={() => { setEditing(a); setEditTime(clock(a.scheduled_time)); setEditDuration(a.duration_minutes); }}>修改{a.display_name}的时间或时长</button>)}{arrangement.items.filter(i => i.kind === "free_window" && i.day_date === d.date).map(i => <article className="natural-free" key={i.id}><strong>{clock(i.start)}—{clock(i.end)} · {i.label}</strong><span>有意保留，不自动填满</span></article>)}<button disabled={busy || d.activities.length < 2} onClick={() => void task(async () => { const value = await naturalRequest<{ legs: { duration_minutes: number; provider: string; is_estimated: boolean }[] }>(`/day-plans/${d.id}/route`); setRoute({ day: d.date, legs: value.legs }); })}>查看活动间路线，不改时间</button></section>)}
        {route && <section className="natural-route" aria-label="路线查询结果"><h3>{route.day} 路线参考</h3>{route.legs.map((leg, n) => <p key={n}>第{n + 1}段 · 预计{leg.duration_minutes}分钟 · {leg.is_estimated ? "估算，尚未核实" : leg.provider}</p>)}<p>此次查询没有修改活动时间或保存新的安排。</p></section>}
        {editing && <form className="natural-editor" onSubmit={saveActivity}><h3>修改{editing.display_name}</h3><label>开始时间<input aria-label="活动开始时间" type="time" required value={editTime} onChange={e => setEditTime(e.target.value)} /></label><label>停留分钟<input aria-label="活动停留分钟" type="number" min={5} max={1440} required value={editDuration} onChange={e => setEditDuration(Number(e.target.value))} /></label><button disabled={busy}>保存这次修改</button><button type="button" onClick={() => setEditing(undefined)}>暂不修改</button></form>}
        {arrangement.items.some(i => i.kind === "cancelled") && <details><summary>已撤销的选择</summary>{arrangement.items.filter(i => i.kind === "cancelled").map(i => <p key={i.id}>{i.label} · 原决定来源保留</p>)}</details>}
      </>}
    </aside>{error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}</section>;
}
