import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ApiTripPlanningRepository } from "../data/apiTripPlanningRepository";
import { PlaceContentRepository } from "../data/placeContentRepository";
import type { Activity, Trip, TripPlanningRepository } from "../domain/types";
import type { ExplorePlace, ExplorePoint } from "../domain/explore";
import { ExploreMap } from "../product/ExploreMap";
import { activityPoint, externalRoute, queryJourneyRoute, safeReturnTo, type JourneyRouteResult, type RouteOrigin } from "./routeModel";
import "./journeyRouting.css";

const api = new ApiTripPlanningRepository();
const places = new PlaceContentRepository();
interface Scene { origin: RouteOrigin | null; mode: "walk" | "driving"; result: JourneyRouteResult | null;
  query: string; map?: { center: ExplorePoint; zoom: number }; destination?: ExplorePoint }
const empty = (): Scene => ({ origin: null, mode: "walk", result: null, query: "" });
function restore(key: string): Scene {
  try { const stored = JSON.parse(sessionStorage.getItem(key) ?? "null");
    return stored && ["walk", "driving"].includes(stored.mode) ? stored : empty(); } catch { return empty(); }
}
export function JourneyRoutePage({ repository = api }: { repository?: Pick<TripPlanningRepository, "getTrip" | "getDays"> }) {
  const { tripId = "", activityId = "" } = useParams();
  const [params] = useSearchParams();
  const key = `roamsync:journey-route:v1:${tripId}:${activityId}`;
  const routeEpoch = useRef(0);
  const [scene, setScene] = useState<Scene>(() => restore(key));
  const [trip, setTrip] = useState<Trip | null>(null);
  const [target, setTarget] = useState<Activity | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [searching, setSearching] = useState(false);
  const [results, setResults] = useState<ExplorePlace[]>([]);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const fromId = params.get("fromActivityId");
  const returnTo = safeReturnTo(params.get("returnTo"), tripId);
  useEffect(() => {
    routeEpoch.current++; setBusy(false);
    let live = true; setLoading(true); setError(""); setTarget(null); setTrip(null);
    Promise.all([repository.getTrip(tripId), repository.getDays(tripId)]).then(([nextTrip, days]) => {
      if (!live) return;
      const all = days.flatMap(day => day.activities);
      const next = all.find(item => item.id === activityId);
      if (!next) throw new Error("这项活动已不在当前正式安排中，请返回日程查看。");
      setTrip(nextTrip); setActivities(all); setTarget(next);
      const saved = restore(key); const point = activityPoint(next);
      const previous = all.find(item => item.id === fromId) ?? all[all.indexOf(next) - 1];
      const previousPoint = previous && activityPoint(previous);
      if (!saved.origin && previousPoint) saved.origin = { point: previousPoint, name: previous.name, activityId: previous.id };
      // Restore formal origins only from the latest server snapshot.
      if (saved.origin?.activityId) {
        const current = all.find(item => item.id === saved.origin?.activityId);
        const currentPoint = current && activityPoint(current);
        saved.origin = current && currentPoint ? { name: current.name, point: currentPoint, activityId: current.id } : null;
      }
      if (JSON.stringify(saved.destination) !== JSON.stringify(point) ||
          JSON.stringify(saved.origin) !== JSON.stringify(restore(key).origin)) saved.result = null;
      saved.destination = point ?? undefined;
      setScene(saved);
    }).catch(reason => { if (live) setError(reason instanceof Error ? reason.message : "日程暂时无法读取。"); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; routeEpoch.current++; };
  }, [tripId, activityId, fromId, repository, key, retry]);
  useEffect(() => { if (!loading && target) { try { sessionStorage.setItem(key, JSON.stringify(scene)); } catch { /* Browsing remains usable without persistence. */ } } }, [key, scene, loading, target]);
  const destination = target ? activityPoint(target) : null;
  function selectOrigin(origin: RouteOrigin) { routeEpoch.current++; setBusy(false); setScene(current => ({ ...current, origin, result: null })); setError(""); }
  async function search() {
    if (!trip || !scene.query.trim()) return;
    setSearching(true); setError("");
    try { setResults((await places.search({ city: trip.destination, q: scene.query })).items); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "地点搜索失败。"); }
    finally { setSearching(false); }
  }
  async function route() {
    if (!scene.origin || !destination) return;
    const epoch = ++routeEpoch.current;
    const signature = JSON.stringify([scene.origin.point, destination, scene.mode]);
    setBusy(true); setError("");
    try { const result = await queryJourneyRoute(scene.origin.point, destination, scene.mode);
      if (epoch === routeEpoch.current) setScene(current => JSON.stringify([current.origin?.point, current.destination, current.mode]) === signature ? { ...current, result } : current);
    }
    catch (reason) { if (epoch === routeEpoch.current) setError(reason instanceof Error ? reason.message : "路线查询失败。"); }
    finally { if (epoch === routeEpoch.current) setBusy(false); }
  }
  return <main className="journey-route">
    <Link to={returnTo}>← 返回旅行安排</Link>
    <header><p>{trip?.title ?? "旅行路线"}</p><h1>{target ? `前往 ${target.name}` : "查看路线"}</h1></header>
    {loading && <p role="status">正在读取最新日程…</p>}
    {error && <div role="alert"><p>{error}</p>{!target && <button onClick={() => setRetry(value => value + 1)}>重新读取</button>}</div>}
    {!loading && target && !destination && <p>这项活动缺少可确认来源的地图坐标，暂时无法查询路线。请返回日程查看地点信息。</p>}
    {!loading && target && destination && <div className="journey-route-grid">
      <section className="journey-route-controls"><h2>从哪里出发</h2>
        <label>旅行中的地点<select aria-label="选择正式活动作为起点" value={scene.origin?.activityId ?? ""} disabled={busy} onChange={event => {
          const item = activities.find(activity => activity.id === event.target.value); const point = item && activityPoint(item);
          if (item && point) selectOrigin({ point, name: item.name, activityId: item.id });
        }}><option value="">选择日程中的地点</option>{activities.filter(item => item.id !== activityId && activityPoint(item)).map(item => <option key={item.id} value={item.id}>{item.scheduledTime} · {item.name}</option>)}</select></label>
        <form onSubmit={event => { event.preventDefault(); void search(); }}><label>搜索其他出发地点<input value={scene.query} onChange={event => setScene(current => ({ ...current, query: event.target.value }))} placeholder={`${trip?.destination ?? "目的地"}的地点名称`} /></label><button disabled={searching || !scene.query.trim()}>{searching ? "搜索中…" : "搜索地点"}</button></form>
        {results.length > 0 && <ul className="journey-route-results">{results.map(place => <li key={place.id}><button disabled={busy} onClick={() => selectOrigin({ point: place.location, name: place.name })}>{place.name}<small>{place.address}</small></button></li>)}</ul>}
        <p>也可以点击地图选择出发位置。</p><p className="journey-route-origin">起点：{scene.origin?.name ?? "尚未选择"}</p>
        <label>出行方式<select aria-label="出行方式" disabled={busy} value={scene.mode} onChange={event => setScene(current => ({ ...current, mode: event.target.value as Scene["mode"], result: null }))}><option value="walk">步行</option><option value="driving">驾车</option></select></label>
        <button className="journey-route-primary" disabled={!scene.origin || busy} onClick={() => void route()}>{busy ? "正在查询路线…" : "查询路线"}</button>
        {scene.result && scene.origin && <section aria-label="路线结果"><h2>{scene.mode === "walk" ? "步行" : "驾车"}路线</h2><p>{(scene.result.distance_meters / 1000).toFixed(1)} 公里 · 约 {Math.ceil(scene.result.duration_seconds / 60)} 分钟</p><p>高德路线预计用时，实际交通情况可能变化。</p><a href={externalRoute(scene.origin, destination, target.name, scene.mode)} target="_blank" rel="noreferrer">用高德地图出发 ↗</a><p className="journey-route-muted">打开外部地图查询与导航；返回这里可继续查看日程。</p></section>}
      </section>
      <section><ExploreMap center={destination} points={[{ point: destination, label: target.name, id: "destination" }, ...(scene.origin ? [{ point: scene.origin.point, label: scene.origin.name, id: "origin" }] : [])]} path={scene.result?.path.map(point => [point.longitude, point.latitude]) ?? []} pickMode={!busy} onPickPoint={point => selectOrigin({ point, name: "地图所选位置" })} savedView={scene.map} onViewChange={map => setScene(current => ({ ...current, map }))} ariaLabel="旅行活动路线地图" /></section>
    </div>}
  </main>;
}
