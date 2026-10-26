import { Check, MapPin, Plus, Search, Star, X } from "lucide-react";
import { useMemo, useState } from "react";
import type { PlaceCategory, PlaceOption } from "../domain/types";
import { formatFen } from "../utils/planner";

const filters: Array<{ value: "all" | PlaceCategory; label: string }> = [
  { value: "all", label: "全部" },
  { value: "sight", label: "景点" },
  { value: "nature", label: "自然" },
  { value: "culture", label: "人文" },
  { value: "food", label: "餐饮" },
];

interface PlacesDrawerProps {
  open: boolean;
  candidates: PlaceOption[];
  dayLabel: string;
  destination: string;
  onClose: () => void;
  onAdd: (place: PlaceOption) => Promise<void>;
  onSearch: (query: string, category?: PlaceCategory) => Promise<void>;
}

export function PlacesDrawer({ open, candidates, dayLabel, destination, onClose, onAdd, onSearch }: PlacesDrawerProps) {
  const [filter, setFilter] = useState<"all" | PlaceCategory>("all");
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);
  const filtered = useMemo(
    () => candidates.filter((candidate) => (filter === "all" || candidate.category === filter) && candidate.name.includes(query.trim())),
    [candidates, filter, query],
  );
  if (!open) return null;

  async function add(place: PlaceOption) {
    const key = placeKey(place);
    setAdding(key);
    try { await onAdd(place); } finally { setAdding(null); }
  }

  async function searchPlaces() {
    setSearching(true);
    try { await onSearch(query, filter === "all" ? undefined : filter); } finally { setSearching(false); }
  }

  return (
    <div className="drawer-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="places-drawer" aria-label="候选地点" data-testid="places-drawer">
        <header>
          <div><span className="eyebrow">PLACE LIBRARY</span><h2>加入 {dayLabel}</h2></div>
          <button type="button" className="close-button dark" onClick={onClose} aria-label="关闭候选地点"><X size={19} /></button>
        </header>
        <form className="search-form" onSubmit={(event) => { event.preventDefault(); void searchPlaces(); }}><label className="search-field"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={`搜索${destination}地点`} /></label><button type="submit" disabled={searching}>{searching ? "搜索中" : "搜索"}</button></form>
        <div className="filter-row">
          {filters.map((item) => <button key={item.value} type="button" className={filter === item.value ? "is-active" : ""} onClick={() => setFilter(item.value)}>{item.label}</button>)}
        </div>
        <div className="candidate-list">
          {filtered.length === 0 ? <div className="no-results"><Search size={26} /><strong>没有匹配地点</strong><p>清除关键词或切换分类。</p></div> : filtered.map((place) => (
            <article key={placeKey(place)} className={`candidate-card category-${place.category}`}>
              <div className="candidate-visual"><span>{place.name.slice(0, 1)}</span></div>
              <div className="candidate-copy">
                <div className="candidate-title"><strong>{place.name}</strong><span><Star size={12} fill="currentColor" />{place.rating}</span></div>
                <p className="candidate-location"><MapPin size={12} />{place.neighborhood} · {place.suggestedDurationMinutes} 分钟</p>
                <p>{place.description}</p>
                <div className="tag-row">{place.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
              </div>
              <div className="candidate-action"><strong>{place.estimatedCostFen ? formatFen(place.estimatedCostFen) : "免费"}</strong><button type="button" disabled={adding === placeKey(place)} onClick={() => void add(place)}>{adding === placeKey(place) ? <Check size={17} /> : <Plus size={17} />} 确认加入</button></div>
            </article>
          ))}
        </div>
        <footer><span>高德 POI · 实时数据</span><p>搜索结果不会保存，只有确认加入后才写入行程。</p></footer>
      </aside>
    </div>
  );
}

function placeKey(place: PlaceOption) {
  return "kind" in place ? `${place.provider}:${place.providerPoiId}` : place.id;
}
