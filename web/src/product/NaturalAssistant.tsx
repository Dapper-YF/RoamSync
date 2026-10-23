import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import "./NaturalAssistant.css";

type Choice = { id: string; kind: "selected" | "optional" | "free_window" | "cancelled"; label: string; source_ref: string; decision_ref: string; place_id: string | null; day_date: string | null; start: string | null; end: string | null; activity_id: string | null };
type Activity = { id: string; place_id: string; name: string; display_name: string; scheduled_time: string; duration_minutes: number; schedule_locked: boolean; version: number; note: string | null };
type Day = { id: string; date: string; activities: Activity[]; route_legs: { duration_minutes: number; is_estimated: boolean }[] };
type Trip = { id: string; title: string; destination: string; start_date: string; end_date: string; version: number };
type Arrangement = { version: number; trip: Trip; days: Day[]; items: Choice[] };
type PreviewChoice = { kind: string; label: string; origin: string; day_date: string | null; start: string | null; end: string | null };
type Preview = { id: string; title: string; start_date: string; end_date: string; summary: string; flexible?: boolean; choices?: PreviewChoice[] };
type Turn = { id: string; user: string; assistant: string; context?: { topic_id?: string } };
type Session = { id: string; trip_id: string | null; messages: Turn[]; pending_action: Preview | null; latest_run_id: string | null };
type Run = { id: string; status: string; error_message: string | null; response_text: string | null; pending_interrupt?: { kind: string; revision_id?: string; questions?: string[] } | null };
type PlaceResult = { name: string; provider_place_id: string; address?: string; [key: string]: unknown };
type Revision = { id: string; status: string; reason: string; proposed_snapshot: { activities: { candidate_id: string; replaces_activity_id: string | null; place_candidate_id: string; day_date: string; planned_start_time: string; duration_minutes: number; reason?: string }[]; route_legs?: { duration_minutes: number; provider: string; is_estimated: boolean }[] }; validation_result: { warnings?: { message: string }[] } };

export async function naturalRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${url}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    const message = response.status === 409 ? "这份安排刚刚有了新修改。本次操作没有覆盖它，请核对最新内容后再试。" :
      typeof detail === "string" ? detail : detail?.message ?? detail?.errors?.[0]?.message ?? "暂时无法完成操作，请稍后重试。";
    throw new Error(message);
  }
  return response.status === 204 ? undefined as T : response.json();
}
const labels: Record<string, string> = { selected: "已选 · 时间未定", optional: "备选 · 可以不去", free_window: "保留空闲", blank_day: "整天留白", cancelled: "已撤销", appointment: "你提供的固定预约" };
const clock = (v: string | null | undefined) => v?.slice(0, 5) ?? "";
const key = (trip?: string) => `roamsync.natural.session.${trip ?? "new"}`;
const topic = "natural-travel";

export function NaturalArrangements() {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { naturalRequest<Trip[]>("/trips").then(setTrips).catch(e => setError(e.message)); }, []);
  return <main className="natural-home"><p className="natural-eyebrow">按自己的节奏旅行</p><h1>我的安排</h1><p>保留已经决定的，其他的可以慢慢想。</p><Link className="natural-primary" to="/">和助手聊一聊</Link>{error && <p role="alert">{error}</p>}<div className="natural-trip-list">{trips.map(t => <Link key={t.id} to={`/arrangements/${t.id}`}><strong>{t.title}</strong><span>{t.destination} · {t.start_date} — {t.end_date}</span></Link>)}</div>{!trips.length && !error && <p>还没有保存的安排。可以先问一个旅行问题，不必立即决定出发。</p>}</main>;
}

export function NaturalAssistant({ contextTripId }: { contextTripId?: string } = {}) {
  const params = useParams();
  const tripId = params.tripId ?? contextTripId;
  const navigate = useNavigate();
  const [session, setSession] = useState<Session>();
  const [arrangement, setArrangement] = useState<Arrangement>();
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [run, setRun] = useState<Run>();
  const [revision, setRevision] = useState<Revision>();
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
  const reload = useCallback(async () => {
    if (!tripId) { setArrangement(undefined); return; }
    setArrangement(await naturalRequest<Arrangement>(`/trips/${tripId}/arrangement-items`));
  }, [tripId]);
  useEffect(() => {
    let active = true;
    setError(""); setSession(undefined); setRun(undefined); setRevision(undefined); setRoute(undefined); setEditing(undefined);
    void reload().catch(e => { if (active) setError(e.message); });
    const restore = async () => {
      const saved = localStorage.getItem(key(tripId));
      const value = await naturalRequest<Session>("/assistant/sessions", { method: "POST", body: JSON.stringify(saved ? { session_id: saved, ...(tripId ? { trip_id: tripId } : {}) } : tripId ? { trip_id: tripId } : {}) });
      if (active) { setSession(value); localStorage.setItem(key(tripId), value.id); }
    };
    void restore().catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [tripId, reload]);
  const runId = session?.latest_run_id;
  useEffect(() => {
    if (!runId) return;
    let active = true;
    let interval: ReturnType<typeof setInterval> | undefined;
    const poll = async () => {
      try {
        const value = await naturalRequest<Run>(`/planning-runs/${runId}`);
        if (!active) return;
        setRun(value);
        if (value.status === "awaiting_confirmation") {
          const proposal = await naturalRequest<Revision>(`/planning-runs/${runId}/revision`);
          if (active) setRevision(proposal);
        } else if (["accepted", "rejected", "cancelled", "failed", "answered"].includes(value.status)) {
          setRevision(undefined);
          if (interval !== undefined) clearInterval(interval);
        }
      } catch (e) { if (active) setError((e as Error).message); }
    };
    void poll(); interval = setInterval(() => void poll(), 2500);
    return () => { active = false; clearInterval(interval); };
  }, [runId]);
  async function task(operation: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await operation(); } catch (e) { setError((e as Error).message); await reload().catch(() => {}); }
    finally { setBusy(false); }
  }
  async function receive(value: Session) {
    setSession(value);
    if (value.trip_id && value.trip_id !== tripId) {
      localStorage.setItem(key(value.trip_id), value.id); localStorage.removeItem(key()); navigate(`/arrangements/${value.trip_id}`);
    } else await reload();
  }
  async function send(event: FormEvent) {
    event.preventDefault(); if (!draft.trim() || !session || busy) return;
    const message = draft.trim();
    await task(async () => {
      const mid = crypto.randomUUID();
      const simple = /改成备选|改为备选|设为备选|作为备选|^(?:请)?保留|^(?:今天)?(?:不想去|不去|取消)/.test(message)
        || /^[^，。；]+(?:还是|仍是|仍为)备选(?:[，,](?:不要|别)(?:把它)?排进去)?[。！! ]*$/.test(message);
      const adopt = /^(?:就按这份来|就这样安排|采用这份方案|确认采用)[。！! ]*$/.test(message);
      const context = { version: "assistant-context-v1", topic_id: topic, surface: tripId ? "trip" : "assistant", prefer_flexible: true,
        ...(tripId ? { read_trip_id: tripId, browsing_city: arrangement?.trip.destination,
          action_target: { trip_id: tripId, expected_version: arrangement?.version, operation: adopt && revision ? "accept_plan" : simple ? "edit_arrangement" : "plan_trip", authorization_message_id: mid,
            ...(adopt && revision ? { revision_id: revision.id } : {}) } } : {}),
        ...(adopt && session.pending_action ? { preview_action_id: session.pending_action.id } : {}) };
      const value = await naturalRequest<Session>(`/assistant/sessions/${session.id}/messages`, { method: "POST", body: JSON.stringify({ message, message_id: mid, context }) });
      setDraft(""); await receive(value);
    });
  }
  async function adoptPreview() {
    if (!session?.pending_action) return;
    await task(async () => receive(await naturalRequest<Session>(`/assistant/sessions/${session.id}/decision`, {
      method: "POST", body: JSON.stringify({ action_id: session.pending_action!.id, accept: true }) })));
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
  async function decideRevision(accept: boolean) {
    if (!revision) return;
    await task(async () => { await naturalRequest(`/plan-revisions/${revision.id}/${accept ? "accept" : "reject"}`, { method: "POST" }); setRevision(undefined); await reload(); setNotice(accept ? "已采用调整，保存后的安排已更新。" : "未采用，原安排保持不变。"); });
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
  const turns = session?.messages.filter(t => !t.context?.topic_id || t.context.topic_id === topic) ?? [];
  const activities = arrangement?.days.flatMap(d => d.activities) ?? [];
  return <main className="natural-workspace">
    <section className="natural-conversation" aria-label="旅行助手">
      <p className="natural-eyebrow">RoamSync · 按自己的节奏</p><h1>{arrangement ? `聊聊${arrangement.trip.destination}这次旅行` : "这次旅行，想从哪里聊起？"}</h1>
      <p>可以只问一个问题，也可以慢慢形成安排。不必先填表，更不必把每天排满。</p>
      {!turns.length && <div className="natural-starters">{["第一次去南京，博物院和玄武湖的体验有什么区别？", "想去南京两天，几个地方已经想好了，其他暂时不定。"].map(text => <button key={text} onClick={() => setDraft(text)}>{text}</button>)}</div>}
      <div className="natural-messages" aria-live="polite">{turns.map(t => <article key={t.id}><p className="natural-user">{t.user}</p><p className="natural-answer">{t.assistant}</p></article>)}</div>
      {session?.pending_action && <section className="natural-preview" aria-label="待采用的安排建议"><h2>这份建议，由你决定</h2><p>{session.pending_action.start_date} — {session.pending_action.end_date}</p><p>{session.pending_action.summary}</p><ul>{session.pending_action.choices?.map((i, n) => <li key={n}><strong>{i.label}</strong> · {labels[i.kind]}{i.kind === "blank_day" && i.day_date && ` · ${i.day_date}`}{i.start && ` · ${i.day_date} ${clock(i.start)}—${clock(i.end)}`}<small>{i.origin === "ai_suggestion" ? "助手建议，采用前可以修改" : "来自你的表达"}</small></li>)}</ul><button disabled={busy} onClick={() => void adoptPreview()}>采用并保存这份安排</button></section>}
      {run && <section className="natural-run" aria-label="调整进展">{["queued", "researching", "planning", "validating"].includes(run.status) && <p>正在核对本次需要协调的安排……</p>}{run.status === "failed" && <p role="alert">这次没能形成可采用的调整。{run.error_message} 原安排保持不变。</p>}{run.status === "awaiting_clarification" && <p>{run.pending_interrupt?.questions?.join(" ")}</p>}</section>}
      {revision?.status === "pending" && <section className="natural-preview" aria-label="局部调整建议"><h2>核对这次调整</h2><p>{revision.reason}</p><ul>{revision.proposed_snapshot.activities.map(i => { const old = activities.find(a => a.id === i.replaces_activity_id || a.place_id === i.place_candidate_id); return <li key={i.candidate_id}>{old?.display_name ?? "新地点（请核对方案说明）"} · {i.day_date}<br />{old ? `原来 ${clock(old.scheduled_time)} / ${old.duration_minutes}分钟 → ` : "建议 "}{clock(i.planned_start_time)} / {i.duration_minutes}分钟{i.reason && <p>{i.reason}</p>}</li>; })}</ul>{revision.proposed_snapshot.route_legs?.map((leg, n) => <p key={n}>路线参考第{n + 1}段：预计{leg.duration_minutes}分钟 · {leg.is_estimated ? "估算，尚未核实" : leg.provider}</p>)}<p>上面的具体时间采用后才会保存；固定活动、留白和其他要求仍会在采用时检查。</p><button disabled={busy} onClick={() => void decideRevision(true)}>采用这次调整</button><button disabled={busy} onClick={() => void decideRevision(false)}>保留原安排</button></section>}
      {error && <p className="natural-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
      <form onSubmit={send} className="natural-composer"><label htmlFor="travel-message">告诉助手你的问题或变化</label><textarea id="travel-message" value={draft} onChange={e => setDraft(e.target.value)} placeholder={arrangement ? "例如：把玄武湖改成备选；或告诉我哪个时间需要协调" : "想了解哪里？已经决定了什么？"} /><button type="submit" disabled={busy || !session || !draft.trim()}>{busy ? "正在处理……" : "发送"}</button></form>
      <p className="natural-limit">实时开放、票价和预约需有来源才能确认；已保存不等于已完成预订。</p>
    </section>
    <aside className="natural-arrangement" aria-label="我的安排"><div className="natural-panel-heading"><h2>我的安排</h2><Link to="/arrangements">查看全部</Link></div>
      {!arrangement && <div className="natural-empty"><h3>先聊聊，也很好</h3><p>明确日期后，可以请助手整理一份允许留白的建议。你采用后，它才会出现在这里。</p></div>}
      {arrangement && <><h3>{arrangement.trip.title}</h3><p>{arrangement.trip.start_date} — {arrangement.trip.end_date}</p><button onClick={() => void task(reload)} disabled={busy}>刷新已保存内容</button>
        <section aria-label="未排程与备选"><h3>想去的与备选</h3>{arrangement.items.filter(i => !i.activity_id && ["selected", "optional"].includes(i.kind)).map(i => <article className="natural-choice" key={i.id}><strong>{i.label}</strong><span>{labels[i.kind]}{i.day_date ? ` · ${i.day_date}` : ""}</span><small>{i.place_id ? "已关联地点身份；时间尚未确定" : "名称来自讨论，具体地点尚未核实"}</small><div><button disabled={busy} onClick={() => void changeChoice(i, i.kind === "selected" ? "optional" : "selected")}>{i.kind === "selected" ? "改为备选" : "确定纳入"}</button><button disabled={busy} onClick={() => { setScheduling(i); setPlaceQuery(i.label); setPlaceResults([]); setSelectedPlace(undefined); setScheduleDay(""); setScheduleTime(""); setScheduleDuration(""); }}>安排具体时间</button><button disabled={busy} onClick={() => void changeChoice(i, "cancelled")}>取消这项</button></div></article>)}</section>
        {scheduling && <form className="natural-editor" aria-label={`为${scheduling.label}安排具体时间`} onSubmit={scheduleChoice}><h3>给{scheduling.label}安排时间</h3>{!scheduling.place_id && <><label>核对地点<input aria-label="排程地点搜索" value={placeQuery} onChange={e => setPlaceQuery(e.target.value)} /></label><button type="button" disabled={busy || !placeQuery.trim()} onClick={() => void task(async () => { setSelectedPlace(undefined); setPlaceResults(await naturalRequest<PlaceResult[]>(`/trips/${tripId}/places/search?q=${encodeURIComponent(placeQuery)}`)); })}>查询实际地点</button>{placeResults.map(p => <button type="button" key={p.provider_place_id} aria-pressed={selectedPlace?.provider_place_id === p.provider_place_id} onClick={() => setSelectedPlace(p)}>{p.name} · {[p.neighborhood, p.address || p.description].filter(Boolean).join(" · ")} · {selectedPlace?.provider_place_id === p.provider_place_id ? "已选择" : "选择此地点"}</button>)}</>}<label>选择日期<select aria-label="排程日期" required value={scheduleDay} onChange={e => setScheduleDay(e.target.value)}><option value="">日期尚未选择</option>{arrangement.days.map(d => <option key={d.id} value={d.id}>{d.date}</option>)}</select></label><label>开始时间<input aria-label="排程开始时间" type="time" required value={scheduleTime} onChange={e => setScheduleTime(e.target.value)} /></label><label>停留分钟<input aria-label="排程停留分钟" type="number" min={5} max={1440} required value={scheduleDuration} onChange={e => setScheduleDuration(e.target.value)} /></label><p>时间和时长由你明确选择，不代表预约或交通已完成核实。</p><button disabled={busy || !scheduling.place_id && !selectedPlace}>保存这项具体安排</button><button type="button" onClick={() => setScheduling(undefined)}>继续保持未定</button></form>}
        <form className="natural-add" onSubmit={addChoice}><label>再记一个地方<input aria-label="事项名称" value={newLabel} onChange={e => setNewLabel(e.target.value)} maxLength={160} /></label><select aria-label="事项选择" value={newKind} onChange={e => setNewKind(e.target.value)}><option value="selected">确定想去，时间未定</option><option value="optional">有时间再去</option></select><button disabled={busy || !newLabel.trim()}>保存这个选择</button></form>
        {arrangement.days.map(d => <section className="natural-day" key={d.id}><h3>{d.date}</h3>{d.activities.map(a => <article className="natural-activity" key={a.id}><span>{clock(a.scheduled_time)} · {a.duration_minutes}分钟</span><strong>{a.display_name}</strong><small>{a.schedule_locked ? "固定活动 · 调整需核对影响" : "具体时间"}</small><div><button disabled={busy} onClick={() => { setEditing(a); setEditTime(clock(a.scheduled_time)); setEditDuration(a.duration_minutes); }}>修改时间或时长</button><Link to={`/trips/${tripId}/route/${a.id}`}>查看出行</Link></div></article>)}{arrangement.items.filter(i => i.kind === "free_window" && i.day_date === d.date).map(i => <article className="natural-free" key={i.id}><strong>{clock(i.start)}—{clock(i.end)} · {i.label}</strong><span>有意保留，不自动填满</span></article>)}{!d.activities.length && <p>这天还没有具体时间安排，可以继续留空。</p>}{d.activities.length > 1 && d.route_legs.length < d.activities.length - 1 && <p>活动间路线尚未核实，当前时间只是已保存的选择；可先查询，再决定是否协调。</p>}<button disabled={busy || d.activities.length < 2} onClick={() => void task(async () => { const value = await naturalRequest<{ legs: { duration_minutes: number; provider: string; is_estimated: boolean }[] }>(`/day-plans/${d.id}/route`); setRoute({ day: d.date, legs: value.legs }); })}>查看活动间路线，不改时间</button></section>)}
        {route && <section className="natural-route" aria-label="路线查询结果"><h3>{route.day} 路线参考</h3>{route.legs.map((leg, n) => <p key={n}>第{n + 1}段 · 预计{leg.duration_minutes}分钟 · {leg.is_estimated ? "估算，尚未核实" : leg.provider}</p>)}<p>此次查询没有修改活动时间或保存新的安排。</p></section>}
        {editing && <form className="natural-editor" onSubmit={saveActivity}><h3>修改{editing.display_name}</h3><label>开始时间<input aria-label="活动开始时间" type="time" required value={editTime} onChange={e => setEditTime(e.target.value)} /></label><label>停留分钟<input aria-label="活动停留分钟" type="number" min={5} max={1440} required value={editDuration} onChange={e => setEditDuration(Number(e.target.value))} /></label><button disabled={busy}>保存这次修改</button><button type="button" onClick={() => setEditing(undefined)}>暂不修改</button></form>}
        {arrangement.items.some(i => i.kind === "cancelled") && <details><summary>已撤销的选择</summary>{arrangement.items.filter(i => i.kind === "cancelled").map(i => <p key={i.id}>{i.label} · 原决定来源保留</p>)}</details>}
      </>}
    </aside>
  </main>;
}
