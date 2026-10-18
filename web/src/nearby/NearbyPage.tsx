import { useEffect, useRef, useState } from "react";
import { PlaceCover } from '../components/PlacePhotos';
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Check, LocateFixed, MapPin, Search, Sparkles, X } from "lucide-react";
import { PlaceContentRepository } from "../data/placeContentRepository";
import type { ExploreCategory, ExplorePlace, ExplorePoint } from "../domain/explore";
import { ExploreMap } from "../product/ExploreMap";
import { useTravelAssistant } from "../product/TravelAssistant";
import { useScene } from "../discovery/scene";
import { distanceLabel, distanceMeters, useNearbyState, wgs84ToGcj02, type NearbyQuery } from "./state";
import "./nearby.css";

const repository = new PlaceContentRepository();
const categories: Array<[ExploreCategory, string]> = [["all", "全部"], ["food", "餐饮"], ["sight", "景点"], ["hotel", "住宿"]];
const problem = (e: unknown) => e instanceof Error ? e.message : "服务暂不可用，请稍后重试。";
export function NearbyPage() {
  const [s, update] = useNearbyState();
  const { remember, scene, update: updateScene } = useScene();
  const assistant = useTravelAssistant(), navigate = useNavigate();
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [candidates, setCandidates] = useState<ExplorePlace[]>([]);
  const request = useRef(0);

  useEffect(() => { window.scrollTo(0, s.scroll); return () => { request.current++; }; }, []);
  async function validateCity(input: string) {
    const r = await fetch(`/api/v1/locations/cities?${new URLSearchParams({ keyword: input.trim() })}`);
    if (!r.ok) throw Error("城市查询暂不可用，请稍后重试。");
    const rows = await r.json() as Array<{ name: string; longitude: number; latitude: number }>;
    const city = rows.find(c => c.name.replace(/市$/, "") === input.trim().replace(/市$/, ""));
    if (!city || !Number.isFinite(city.longitude) || !Number.isFinite(city.latitude)) throw Error("没有确认这个城市，请填写完整城市名后重试。");
    return city;
  }
  function setCenter(center: ExplorePoint, name: string, city = s.city) {
    update({ center, centerName: name, city, cityInput: city, mapView: { center, zoom: 15 }, mapRevision: s.mapRevision + 1 });
    setCandidates([]);
  }
  async function findCenter() {
    const id = ++request.current; setBusy("center"); setError("");
    try {
      const city = await validateCity(s.cityInput);
      if (!s.centerInput.trim()) {
        if (id === request.current) setCenter({ longitude: city.longitude, latitude: city.latitude, coordinate_system: "gcj02" }, `${city.name}中心（可在地图调整）`, city.name);
      } else {
        const results = await repository.search({ city: city.name, q: s.centerInput.trim(), category: "all" });
        if (id !== request.current) return;
        update({ city: city.name, cityInput: city.name }); setCandidates(results.items);
        if (!results.items.length) throw Error("没有找到这个出发位置，试试车站、酒店或更具体的地点名称。");
      }
    } catch (e) { if (id === request.current) setError(problem(e)); }
    finally { if (id === request.current) setBusy(""); }
  }
  async function locate() {
    const id = ++request.current; setBusy("location"); setError("");
    try {
      const city = await validateCity(s.cityInput);
      if (!navigator.geolocation) throw Error("这个浏览器暂不支持定位，请手动选择位置。");
      const p = await new Promise<GeolocationPosition>((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }));
      if (id !== request.current) return;
      if (Date.now() - p.timestamp > 120000 || !Number.isFinite(p.coords.accuracy) || p.coords.accuracy > 1500) throw Error("当前位置不够准确，请重试或手动选择位置。");
      const point = wgs84ToGcj02(p.coords.longitude, p.coords.latitude);
      if (distanceMeters(point, { longitude: city.longitude, latitude: city.latitude, coordinate_system: "gcj02" }) > 100000) throw Error("定位与所选城市相距较远，请检查城市或手动选点。");
      setCenter(point, `我的位置（精度约${Math.round(p.coords.accuracy)}米）`, city.name);
    } catch (e) { if (id === request.current) setError(typeof e === "object" && e && "code" in e ? "未能获取定位。请允许浏览器定位，或使用城市、地点和地图手动选点。" : problem(e)); }
    finally { if (id === request.current) setBusy(""); }
  }
  function query(center = s.center): NearbyQuery {
    if (!center || !s.city || s.cityInput.trim().replace(/市$/, "") !== s.city.replace(/市$/, "")) throw Error("先确认所在城市和搜索中心，再寻找附近地点。");
    return { city: s.city, query: s.query.trim(), category: s.category, center, radius_meters: s.radius, min_rating: s.rating ? Number(s.rating) : undefined, max_food_price_yuan: s.category === "food" && s.price ? Number(s.price) : undefined, include_unknown: s.includeUnknown };
  }
  async function search(center?: ExplorePoint, name?: string) {
    const id = ++request.current; setError("");
    try {
      const applied = query(center); setBusy("results");
      const results = await repository.discover({ city: applied.city, q: applied.query, category: applied.category }, { center: applied.center, radius: applied.radius_meters, min_rating: applied.min_rating, max_food_price_yuan: applied.max_food_price_yuan, include_unknown: applied.include_unknown, use_preferences: false });
      if (id !== request.current) return;
      // Defensive distance check: map and list always use this same provider set.
      results.items = results.items.filter(p => distanceMeters(applied.center, p.location) <= applied.radius_meters && (applied.category === "all" || p.category === applied.category));
      results.items.forEach(remember);
      update({ results, applied, selected: results.items.find(p => p.id === s.selected)?.id, ...(center ? { center, centerName: name || "地图当前区域" } : {}) });
    } catch (e) { if (id === request.current) setError(problem(e)); }
    finally { if (id === request.current) setBusy(""); }
  }
  function leave(p: ExplorePlace) { remember(p); update({ scroll: window.scrollY }); updateScene({ returnTo: "/nearby" }); }
  function route(p: ExplorePlace) {
    leave(p);
    if (s.applied && !scene.routes[p.id]?.origin) updateScene({ returnTo: "/nearby", routes: { ...scene.routes, [p.id]: { origin: s.applied.center, originName: "附近搜索中心", query: "", mode: scene.routes[p.id]?.mode ?? "walk" } } });
    navigate(`/places/${p.id}/route`, { state: { from: "/nearby" } });
  }
  function compare(p: ExplorePlace) {
    if (s.compared.some(c => c.id === p.id)) update({ compared: s.compared.filter(c => c.id !== p.id) });
    else if (s.compared.length < 8) update({ compared: [...s.compared, p] });
    else setError("最多同时比较8个地点，请先移除一个。");
  }
  function ask(places: ExplorePlace[]) {
    if (!s.applied) return;
    const context = { places, place: places.length === 1 ? places[0] : undefined, city: s.applied.city, discovery: s.applied, returnTo: "/nearby", prompt: `请结合我当前的附近筛选条件${places.length > 1 ? "比较" : "介绍"}这${places.length}个真实地点：${places.map(p => p.name).join("、")}。请比较已查询到的地址、评分、餐饮参考消费和距搜索中心的直线距离，并给出选择建议；缺失字段明确写未知。` };
    assistant.openAssistant(context);
  }
  const dirty = (() => { try { return JSON.stringify(query()) !== JSON.stringify(s.applied); } catch { return true; } })();
  const moved = s.center && s.mapView && distanceMeters(s.center, s.mapView.center) > 50;
  const selected = s.results?.items.find(p => p.id === s.selected);
  const facts = (p: ExplorePlace) => <><span>{s.applied ? `直线约${distanceLabel(distanceMeters(s.applied.center, p.location))}` : "距离暂无"}</span><span>{p.rating == null ? "评分暂无" : `${p.rating} / 5`}</span><span>{p.reference_cost_yuan == null ? "参考消费暂无" : `约¥${p.reference_cost_yuan}/人`}</span></>;
  const actions = (p: ExplorePlace) => <div className="nearby-place-actions"><Link to={`/places/${p.id}`} state={{ from: "/nearby" }} onClick={() => leave(p)}>查看详情 <ArrowRight size={14}/></Link><button onClick={() => route(p)}>怎么去</button><button aria-pressed={s.compared.some(c => c.id === p.id)} onClick={() => compare(p)}>{s.compared.some(c => c.id === p.id) ? "已加入比较" : "加入比较"}</button></div>;
  return <main className="rxp-page nearby-page">
    <div className="nearby-heading"><span className="rxp-eyebrow">此刻，去一个合适的地方</span><h1>下一站，<em>就在附近。</em></h1><p>选定你想出发的位置，再找一间餐厅、一处风景。无需创建旅行计划。</p></div>
    <section className="nearby-center-panel" aria-label="选择搜索中心"><h2><MapPin size={19}/> 从哪里开始？</h2><form onSubmit={e => { e.preventDefault(); void findCenter(); }}><label>所在城市<input aria-label="附近所在城市" value={s.cityInput} onChange={e => update({ cityInput: e.target.value })} placeholder="输入城市名称" maxLength={100}/></label><label>搜索中心 <small>可填酒店、车站或地点</small><input aria-label="搜索中心名称" value={s.centerInput} onChange={e => update({ centerInput: e.target.value })} placeholder="留空选择城市中心" maxLength={100}/></label><button disabled={!!busy || !s.cityInput.trim()}><Search size={16}/>{busy === "center" ? "查找中…" : "查找位置"}</button><button type="button" disabled={!!busy || !s.cityInput.trim()} onClick={() => void locate()}><LocateFixed size={16}/>{busy === "location" ? "定位中…" : "使用我的位置"}</button></form><small>定位仅在你点击后请求授权；请先填写所在城市。也可完全使用手动选点。</small>{candidates.length > 0 && <div className="nearby-center-candidates">{candidates.map(p => <button key={p.id} onClick={() => setCenter(p.location, p.name, p.city || s.city)}>{p.name}<small>{p.address}</small></button>)}</div>}{s.center && <p className="nearby-center-confirmed"><Check size={16}/>{s.centerName}<small>地图点选可以更改中心，更改后点击“寻找附近”生效。</small></p>}</section>
    <form className="nearby-filters" onSubmit={e => { e.preventDefault(); void search(); }}><label>想找什么<input aria-label="附近关键词" value={s.query} onChange={e => update({ query: e.target.value })} placeholder="如：茶馆、面馆、公园" maxLength={100}/></label><label>类别<select aria-label="附近类别" value={s.category} onChange={e => update({ category: e.target.value as ExploreCategory })}>{categories.map(([v,l]) => <option key={v} value={v}>{l}</option>)}</select></label><label>距离范围<select aria-label="距离范围" value={s.radius} onChange={e => update({ radius: Number(e.target.value) })}>{[500,1000,3000,5000,10000].map(v => <option key={v} value={v}>{distanceLabel(v)}</option>)}</select></label><label>最低评分<select aria-label="最低评分" value={s.rating} onChange={e => update({ rating: e.target.value })}><option value="">不限</option>{[3,3.5,4,4.5].map(v => <option key={v} value={v}>{v}分</option>)}</select></label><label>餐饮人均参考消费<select aria-label="最高参考消费" disabled={s.category !== "food"} value={s.price} onChange={e => update({ price: e.target.value })}><option value="">不限</option>{[30,50,100,200,500].map(v => <option key={v} value={v}>¥{v}以内</option>)}</select></label><label className="nearby-checkbox"><input type="checkbox" checked={s.includeUnknown} onChange={e => update({ includeUnknown: e.target.checked })}/>保留评分或消费未知的地点</label><button className="rxp-primary-action" disabled={!!busy || !s.center}>{busy === "results" ? "正在寻找…" : "寻找附近"}</button></form>
    {error && <div role="alert" className="nearby-error">{error}<button onClick={() => setError("")}>收起</button></div>}
    <section className="nearby-results"><div className="nearby-results-heading"><div><h2>{s.results ? `找到 ${s.results.items.length} 个地点` : "选择位置，开始发现"}</h2>{s.applied && <p>{s.applied.city} · {s.applied.query || categories.find(c => c[0] === s.applied?.category)?.[1]} · {distanceLabel(s.applied.radius_meters)}以内{dirty ? " · 条件已调整，请重新搜索" : ""}</p>}</div><div><button aria-pressed={s.view === "split"} onClick={() => update({ view: "split" })}>地图与列表</button><button aria-pressed={s.view === "list"} onClick={() => update({ view: "list" })}>仅列表</button></div></div>
    <p className="discovery-note">高德真实地点信息；直线距离不代表步行距离。筛选针对本次返回地点，消费仅为餐饮参考，营业和实时库存暂无支持。</p>
    <div className={`nearby-results-layout ${s.view === "list" ? "list-only" : ""}`}>
    {s.view === "split" && s.center && <div className="nearby-map-panel"><div className="nearby-map-help">点击空白地图设置搜索中心；移动地图后点击下方按钮搜索当前区域。</div><ExploreMap key={s.mapRevision} center={s.center} points={(s.results?.items ?? []).map(p => ({ point: p.location, id: p.id, label: p.name }))} selectedId={s.selected} onSelect={id => update({ selected: id })} savedView={s.mapView} onViewChange={mapView => update({ mapView })} pickMode pickLabel="搜索中心" onPickPoint={p => update({ center: p, centerName: "地图选定位置" })} ariaLabel="附近地点地图"/><button className="nearby-search-area" disabled={!moved || !!busy} onClick={() => void search(s.mapView?.center, "地图当前区域")}>搜索此区域</button>{selected && <article className="nearby-selected"><h3>{selected.name}</h3><p>{selected.address}</p><div className="nearby-facts">{facts(selected)}</div>{actions(selected)}<button onClick={() => ask([selected])}><Sparkles size={14}/>问问 AI</button></article>}</div>}
    <div className="nearby-list" aria-busy={busy === "results"}>{busy === "results" && <p role="status">正在查询所选区域的真实地点…</p>}{!s.results && <div className="nearby-empty">{s.center ? "已选好中心，设置条件后点击“寻找附近”。" : "尚未提供位置。填写城市、选择具体地点，或主动授权定位。"}</div>}{s.results && !s.results.items.length && <div className="nearby-empty">没有找到符合条件的地点。试试扩大距离、修改关键词或保留信息未知的地点。</div>}{s.results?.items.map((p,i) => <article key={p.id} className={`nearby-place ${p.id === s.selected ? "selected" : ""}`} data-place-id={p.id}><PlaceCover photos={p.photos}/><button className="nearby-select-place" aria-pressed={p.id === s.selected} onClick={() => update({ selected: p.id })}><span>{i+1}</span><h3>{p.name}</h3></button><p>{p.address || "地址暂无"}</p><div className="nearby-facts">{facts(p)}</div>{actions(p)}</article>)}</div></div></section>
    {s.compared.length > 0 && <section className="nearby-compare"><div className="nearby-compare-heading"><h2>比较候选地点 <small>{s.compared.length}/8</small></h2><button disabled={s.compared.length < 2} onClick={() => update({ compareOpen: !s.compareOpen })}>{s.compareOpen ? "收起对比" : "查看对比"}</button><button disabled={s.compared.length < 2 || !s.applied} onClick={() => ask(s.compared)}><Sparkles size={16}/>请 AI 帮我比较</button></div><div className="nearby-compare-chips">{s.compared.map(p => <button key={p.id} onClick={() => compare(p)}>{p.name}<X size={13}/></button>)}</div>{s.compareOpen && <><div className="nearby-comparison-table"><table><thead><tr><th>地点</th><th>距搜索中心</th><th>评分</th><th>餐饮参考消费</th><th>选择</th></tr></thead><tbody>{s.compared.map(p => <tr key={p.id}><th>{p.name}<small>{p.address || "地址暂无"}</small></th><td>{s.applied ? `直线${distanceLabel(distanceMeters(s.applied.center,p.location))}` : "暂无"}</td><td>{p.rating == null ? "暂无，无法比较评分" : `${p.rating}/5`}</td><td>{p.reference_cost_yuan == null ? "暂无，无法比较消费" : `约¥${p.reference_cost_yuan}/人`}</td><td>{actions(p)}</td></tr>)}</tbody></table></div><p className="discovery-note">比较可保留不同次搜索的候选。距离均按当前已查询中心计算；评分、参考消费来自各地点查询快照，不代表实时报价。开放时间、拥挤度及环境信息暂缺。</p></>}</section>}
  </main>;
}



