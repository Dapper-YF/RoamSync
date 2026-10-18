import { useState } from "react";
import { MapPin, Search } from "lucide-react";
import { PlaceContentRepository } from "../data/placeContentRepository";
import type { DraftItem } from "../data/draftRepository";
import type { ExplorePlace } from "../domain/explore";
import { errorMessage } from "./journeyApi";

const api = new PlaceContentRepository();
export function DraftPlacePicker({ city, disabled, onPick, initialQuery = "" }: { city: string; disabled: boolean; onPick: (item: DraftItem) => void; initialQuery?: string }) {
  const [opened, setOpened] = useState(false);
  const [query, setQuery] = useState(initialQuery);
  const [places, setPlaces] = useState<ExplorePlace[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [searched, setSearched] = useState(false);
  async function search() {
    if (!query.trim()) return; setBusy(true); setError(""); setSearched(true);
    try { setPlaces((await api.search({ city, q: query.trim() })).items); }
    catch (e) { setError(errorMessage(e)); setPlaces([]); } finally { setBusy(false); }
  }
  return <div className="journeys-place-picker"><button disabled={disabled} onClick={() => setOpened(!opened)}><Search size={14} />{opened ? "收起真实地点搜索" : "从真实搜索选择地点"}</button>{opened && <div className="journeys-picker-body"><label>在{city}搜索地点<input disabled={disabled || busy} value={query} placeholder="输入地点名称" onChange={e => { setQuery(e.target.value); setSearched(false); }} onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); void search(); } }} /></label><button disabled={disabled || busy || !query.trim()} onClick={() => void search()}>{busy ? "正在查询…" : "搜索真实地点"}</button>{error && <p role="alert">{error}</p>}{searched && !busy && !error && places.length === 0 && <p>没有匹配地点，可以换一个名称。原活动仍保留。</p>}{places.map(place => <article key={place.id}><strong>{place.name}</strong><p><MapPin size={12} />{place.city} · {place.address || "地址暂缺"}</p><p>{place.rating == null ? "评分未知" : `供应商评分 ${place.rating}`} · {place.reference_cost_yuan == null ? "参考消费未知" : `参考消费 ¥${place.reference_cost_yuan}`}</p><button disabled={disabled || place.freshness === "stale"} onClick={() => { onPick({ name: place.name, note: "", place_id: place.id, identity_status: "provider_confirmed" }); setOpened(false); }}>使用这个地点</button>{place.freshness === "stale" && <p>地点资料已过期，请重新搜索。</p>}</article>)}</div>}</div>;
}
