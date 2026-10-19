import { useEffect, useRef, useState, type ReactNode } from "react";
import { PlaceCover, PlaceGallery } from '../components/PlacePhotos';
import {
  Link,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Compass,
  ExternalLink,
  Heart,
  MapPin,
  Map,
  Navigation,
  Search,
  Sparkles,
  Star,
  Utensils,
  Landmark,
  Hotel,
  List,
} from "lucide-react";
import { PlaceContentRepository } from "../data/placeContentRepository";
import type { ExplorePlace, ExplorePoint } from "../domain/explore";
import {
  TravelAssistantProvider,
  useTravelAssistant,
} from "../product/TravelAssistant";
import { JourneyRoutePage } from "../journeyRouting";
import { NearbyPage } from "../nearby/NearbyPage";
import { JourneysPage, JourneyDraftPage, JourneyPage, type JourneyPageProps } from "../journeys";
import { ExploreMap } from "../product/ExploreMap";
import { DiscoveryState, useScene, type RouteState } from "./scene";
import "../product/ProductExperience.css";
import "./discovery.css";
import { NaturalAssistant, NaturalArrangements } from "../product/NaturalAssistant";
const repository = new PlaceContentRepository();
const categories = [
  ["all", "全部", Compass],
  ["sight", "景点", Landmark],
  ["food", "餐饮", Utensils],
  ["hotel", "住宿", Hotel],
] as const;
export function DiscoveryApp() {
  return (
    <DiscoveryState>
      <TravelAssistantProvider exploreRepository={repository}>
        <Shell />
      </TravelAssistantProvider>
    </DiscoveryState>
  );
}
function Shell() {
  const assistant = useTravelAssistant();
  const location = useLocation();
  const navigate = useNavigate();
  const journeyProps:JourneyPageProps = {
    onAskAssistant: context => assistant.openAssistant({...context, returnTo:location.pathname+location.search}),
    onRoute: context => { if(context.tripId && context.activityId) navigate(`/trips/${context.tripId}/route/${context.activityId}?${new URLSearchParams({...context.fromActivityId?{fromActivityId:context.fromActivityId}:{},returnTo:context.returnTo})}`); }
  };
  const [assistantEntryError, setAssistantEntryError] = useState("");
  async function askOnPage() {
    setAssistantEntryError("");
    const tripId = location.pathname.match(/^\/(?:trips|arrangements)\/([^/]+)/)?.[1];
    const draftId = location.pathname.match(/^\/drafts\/([^/]+)/)?.[1];
    if (tripId) {
      assistant.openAssistant({
        tripId,
        returnTo: location.pathname + location.search,
      });
      return;
    }
    if (draftId && draftId !== "new") {
      try {
        const response = await fetch(
          `/api/v1/drafts/${encodeURIComponent(draftId)}`,
        );
        if (!response.ok) throw Error("暂时无法读取这份草稿，请在草稿中重试。");
        const draft = await response.json();
        assistant.openAssistant({
          draftContext: {
            draftId: draft.id,
            version: draft.version,
            city: draft.city,
          },
          returnTo: location.pathname,
        });
      } catch (e) {
        setAssistantEntryError(message(e));
      }
      return;
    }
    const placeId = location.pathname.match(/^\/places\/([^/]+)/)?.[1];
    if (placeId) {
      try {
        const place = await repository.detail(placeId);
        assistant.openAssistant({
          place,
          returnTo: location.pathname + location.search,
        });
      } catch (e) {
        setAssistantEntryError(message(e));
      }
      return;
    }
    assistant.openAssistant();
  }
  return (
    <div className="rxp-shell discovery-shell">
      <header className="rxp-header">
        <Link to="/" className="rxp-brand">
          <span className="rxp-brand-mark">
            <Compass size={21} />
          </span>
          <span>
            <strong>RoamSync</strong>
            <small>TRAVEL, AT YOUR PACE</small>
          </span>
        </Link>
        <nav className="rxp-nav" aria-label="主导航">
          <NavLink to="/" end className="rxp-nav-link">
            AI 助手
          </NavLink>
          <NavLink to="/arrangements" className="rxp-nav-link">我的安排</NavLink>
          <NavLink to="/explore" className="rxp-nav-link">探索</NavLink>
          <NavLink to="/trips" className="rxp-nav-link">已有旅程</NavLink>
          <NavLink to="/favorites" className="rxp-nav-link">
            收藏
          </NavLink>
        </nav>
        <button
          className="rxp-assistant-button"
          onClick={() => void askOnPage()}
        >
          <Sparkles size={16} />
          旅行助手
        </button>
      </header>
      {assistantEntryError && (
        <p role="alert" className="discovery-entry-error">
          {assistantEntryError}
        </p>
      )}
      <Routes>
        <Route path="/" element={<NaturalAssistant />} />
        <Route path="/arrangements" element={<NaturalArrangements />} />
        <Route path="/arrangements/:tripId" element={<NaturalAssistant />} />
        <Route path="/explore" element={<Discover />} />
        <Route path="/nearby" element={<NearbyPage />} />
        <Route path="/trips" element={<JourneysPage />} />
        <Route path="/drafts" element={<JourneysPage />} />
        <Route path="/drafts/new" element={<JourneysPage />} />
        <Route path="/drafts/:draftId" element={<JourneyDraftPage {...journeyProps} />} />
        <Route path="/trips/:tripId/route/:activityId" element={<JourneyRoutePage />} />
        <Route path="/trips/:tripId" element={<JourneyPage {...journeyProps} />} />
        <Route path="/trips/:tripId/planner" element={<JourneyPage {...journeyProps} />} />
        <Route path="/favorites" element={<Favorites />} />
        <Route path="/places/:placeId" element={<Place />} />
        <Route path="/places/:placeId/map" element={<Place map />} />
        <Route path="/places/:placeId/route" element={<Directions />} />
        <Route
          path="/assistant"
          element={
            <>
              <Back
                to={
                  (location.state as { from?: string } | null)?.from ||
                  assistant.returnTo ||
                  "/"
                }
                label="返回浏览"
              />
              <NaturalAssistant contextTripId={assistant.context.tripId} />
            </>
          }
        />
        <Route
          path="*"
          element={
            <main className="rxp-page">
              <State title="这个页面暂未开放">
                继续探索城市、地点与路线。<Link to="/">回到探索</Link>
              </State>
            </main>
          }
        />
      </Routes>
      <footer className="discovery-footer">
        RoamSync <span>随心探索，从容出发。</span>
        <small>
          {location.pathname === "/assistant"
            ? "与 AI 讨论不会创建或修改正式旅行。"
            : "地点与路线由高德提供 · 信息缺失时如实保留"}
        </small>
      </footer>
    </div>
  );
}
function Back({ to, label = "返回探索" }: { to: string; label?: string }) {
  return (
    <div className="discovery-back">
      <Link className="rxp-back-link" to={to}>
        <ArrowLeft size={16} />
        {label}
      </Link>
    </div>
  );
}
function State({
  title,
  children,
  busy = false,
  error = false,
}: {
  title: string;
  children?: ReactNode;
  busy?: boolean;
  error?: boolean;
}) {
  return (
    <div
      className={`discovery-state ${error ? "error" : ""}`}
      role={error ? "alert" : "status"}
    >
      {busy ? <span className="rxp-spinner" /> : <Compass size={27} />}
      <h2>{title}</h2>
      <div>{children}</div>
    </div>
  );
}
function Discover() {
  const { scene, update, remember } = useScene();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(0);
  const location = useLocation();
  const navigate = useNavigate();
  const assistant = useTravelAssistant();
  useEffect(() => {
    window.scrollTo(0, scene.scroll);
    return () => {
      request.current++;
    };
  }, []);
  async function search(category = scene.category, override?: string) {
    const input = (override ?? scene.input).trim();
    if (!input) {
      setError("输入想去的城市，或地点名称。");
      return;
    }
    const id = ++request.current;
    setBusy(true);
    setError("");
    update({ results: undefined, selected: undefined, scroll: 0 });
    try {
      let city = scene.region.trim();
      let query = input;
      {
        const response = await fetch(
          `/api/v1/locations/cities?${new URLSearchParams({ keyword: input })}`,
        );
        if (!response.ok) throw Error("城市查询暂不可用，请稍后重试。");
        const cities = (await response.json()) as { name: string }[];
        const exact = cities.find(
          (c) => c.name.replace(/市$/, "") === input.replace(/市$/, ""),
        );
        if (exact) {
          city = exact.name;
          query = "";
        } else if (!city)
          throw Error(
            "查找具体地点时，请在“所在城市”中补充搜索范围；城市搜索请使用城市全名。",
          );
      }
      // Validate a manually entered region before handing it to the strict-city POI provider.
      // An unknown city string must not silently turn into a provider default city.
      if (city === scene.region.trim() && query) {
        const response = await fetch(
          `/api/v1/locations/cities?${new URLSearchParams({ keyword: city })}`,
        );
        if (!response.ok) throw Error("城市查询暂不可用，请稍后重试。");
        const regions = (await response.json()) as { name: string }[];
        const exact = regions.find(
          (c) => c.name.replace(/市$/, "") === city.replace(/市$/, ""),
        );
        if (!exact) throw Error("没有确认这个城市，请检查所在城市名称后重试。");
        city = exact.name;
      }
      if (input.replace(/市$/, "") === city.replace(/市$/, "")) query = "";
      const result = await repository.search({ city, q: query, category });
      if (id !== request.current) return;
      result.items.forEach(remember);
      update({
        city,
        query,
        results: result,
        category,
        input,
        region: city,
        maps: { ...scene.maps, search: undefined },
      });
      navigate(`/?${new URLSearchParams({ city, q: query, category })}`, {
        replace: true,
      });
    } catch (e) {
      if (id === request.current) setError(message(e));
    } finally {
      if (id === request.current) setBusy(false);
    }
  }
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const city = params.get("city");
    if (!city) return;
    const query = params.get("q") || "";
    const value = params.get("category");
    const category =
      value === "food" || value === "hotel" || value === "sight"
        ? value
        : "all";
    if (
      scene.results &&
      scene.city === city &&
      scene.query === query &&
      scene.category === category
    )
      return;
    const controller = new AbortController();
    update({
      input: query || city,
      region: city,
      city,
      query,
      category,
      results: undefined,
    });
    setBusy(true);
    setError("");
    void repository
      .search({ city, q: query, category }, controller.signal)
      .then((results) => {
        if (!controller.signal.aborted) update({ results });
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(message(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [location.search]);
  const leave = () =>
    update({
      scroll: window.scrollY,
      returnTo: location.pathname + location.search,
    });
  return (
    <main className="rxp-page discovery-explore">
      <section className={`discovery-hero ${scene.city ? "compact" : ""}`}>
        <div>
          <span className="rxp-eyebrow">去发现，属于你的下一站</span>
          <h1>
            {scene.city ? (
              <>
                在 <em>{scene.city}</em>
                <br />
                找到想去的地方
              </>
            ) : (
              <>
                世界很大，
                <br />
                <em>从你的好奇开始。</em>
              </>
            )}
          </h1>
          <p>
            {scene.city
              ? "逛逛城市，找间餐厅，或选一个地方出发。"
              : "搜索一座城市，或一个心里惦记的地方。无需日期，也无需先制定旅行计划。"}
          </p>
        </div>
        <div className="discovery-art" aria-hidden="true">
          <div className="discovery-orbit" />
          <Compass size={104} strokeWidth={0.6} />
          <span>Take the scenic route.</span>
          <i />
        </div>
      </section>
      <form
        className="discovery-search"
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
      >
        <label>
          <span>想去哪儿？</span>
          <div>
            <Search size={20} />
            <input
              aria-label="城市或地点"
              value={scene.input}
              onChange={(e) => update({ input: e.target.value })}
              placeholder="输入城市，或具体地点名称"
              maxLength={100}
            />
          </div>
        </label>
        <label className="discovery-region">
          <span>
            所在城市 <small>查具体地点时填写</small>
          </span>
          <input
            aria-label="所在城市"
            value={scene.region}
            onChange={(e) => update({ region: e.target.value })}
            placeholder="城市名称"
            maxLength={100}
          />
        </label>
        <button className="rxp-primary-action" disabled={busy}>
          <Search size={17} />
          {busy ? "正在寻找…" : "搜索"}
        </button>
      </form>
      <div className="discovery-tools">
        <div className="discovery-categories">
          {categories.map(([value, label, Icon]) => (
            <button
              type="button"
              key={value}
              className={scene.category === value ? "active" : ""}
              disabled={busy}
              onClick={() => {
                update({ category: value });
                if (scene.input.trim()) void search(value);
              }}
            >
              <Icon size={16} />
              {label}
            </button>
          ))}
        </div>
        {scene.results?.items.length ? (
          <div>
            <button
              aria-pressed={scene.view === "list"}
              onClick={() => update({ view: "list" })}
            >
              <List size={16} />
              列表
            </button>
            <button
              aria-pressed={scene.view === "map"}
              onClick={() => update({ view: "map" })}
            >
              <Map size={16} />
              地图
            </button>
          </div>
        ) : null}
      </div>
      {error ? (
        <State error title="暂时没能完成搜索">
          <p>{error}</p>
          <button onClick={() => void search()}>重新搜索</button>
        </State>
      ) : busy ? (
        <State busy title="正在查询真实地点">
          <p>正在获取地点信息，请稍候。</p>
        </State>
      ) : !scene.results ? (
        <State title="下一站，由你决定">
          <p>从城市名称开始，也可以搜索具体地点并填写所在城市。</p>
          <p>你尚未提供位置。自由探索不需要定位权限。</p>
        </State>
      ) : (
        <section>
          <div className="discovery-results-title">
            <div>
              <span className="rxp-eyebrow">你的探索</span>
              <h2>
                {scene.query || scene.city}{" "}
                <small>{scene.results.items.length} 个地点</small>
              </h2>
            </div>
            <button
              onClick={() =>
                assistant.openAssistant({
                  prompt: `我想了解${scene.city}${scene.query ? "的" + scene.query : ""}，请帮我介绍值得探索的方向。`,
                  city: scene.city,
                })
              }
            >
              <Sparkles size={16} />
              聊聊{scene.city}
            </button>
          </div>
          <p className="discovery-note">
            当前展示高德地点搜索结果。目的地文化专题与开放时间尚无可核实资料，请以当地公告为准。
          </p>
          {!scene.results.items.length ? (
            <State title="没有找到匹配的地点">
              <p>试试更具体的名称，或更换城市和类别。</p>
            </State>
          ) : scene.view === "list" ? (
            <div className="discovery-grid">
              {scene.results.items.map((p) => (
                <Card key={p.id} place={p} onOpen={leave} />
              ))}
            </div>
          ) : (
            <div className="discovery-map-results">
              <div>
                <ExploreMap
                  center={scene.results.items[0].location}
                  points={scene.results.items.map((p) => ({
                    point: p.location,
                    label: p.name,
                    id: p.id,
                  }))}
                  selectedId={scene.selected}
                  onSelect={(id) => update({ selected: id })}
                  savedView={scene.maps.search}
                  onViewChange={(view) =>
                    update({ maps: { ...scene.maps, search: view } })
                  }
                />
                {scene.selected && (
                  <Card
                    place={
                      scene.results.items.find(
                        (p) => p.id === scene.selected,
                      ) ?? scene.results.items[0]
                    }
                    onOpen={leave}
                  />
                )}
              </div>
              <div className="discovery-map-list">
                {scene.results.items.map((p) => (
                  <button
                    key={p.id}
                    className={p.id === scene.selected ? "active" : ""}
                    onClick={() => update({ selected: p.id })}
                  >
                    <MapPin size={16} />
                    <span>
                      <strong>{p.name}</strong>
                      <small>{p.address || p.city}</small>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
function Card({
  place: p,
  onOpen,
}: {
  place: ExplorePlace;
  onOpen?: () => void;
}) {
  const { remember } = useScene();
  return (
    <article className="discovery-card">
      <PlaceCover photos={p.photos} to={`/places/${p.id}`} onOpen={() => { remember(p); onOpen?.(); }} />
      <Link
        to={`/places/${p.id}`}
        onClick={() => {
          remember(p);
          onOpen?.();
        }}
      >
        <div className="discovery-card-icon">
          {p.category === "food" ? (
            <Utensils />
          ) : p.category === "hotel" ? (
            <Hotel />
          ) : (
            <MapPin />
          )}
          <span>
            {p.category === "food"
              ? "餐饮"
              : p.category === "hotel"
                ? "住宿"
                : p.category === "sight"
                  ? "景点"
                  : "地点"}
          </span>
          <ArrowRight size={17} />
        </div>
        <h3>{p.name}</h3>
        <p>
          <MapPin size={14} />
          {p.city} · {p.address || "地址暂缺"}
        </p>
        <div className="discovery-facts">
          <span>
            <Star size={14} />
            {p.rating == null ? "评分暂无" : p.rating.toFixed(1)}
          </span>
          <span>
            {p.reference_cost_yuan == null
              ? "参考消费暂无"
              : `约 ¥${p.reference_cost_yuan}/人`}
          </span>
        </div>
      </Link>
      <footer>
        高德地点信息 <span>查看详情 →</span>
      </footer>
    </article>
  );
}
function usePlace() {
  const { placeId = "" } = useParams();
  const { places, remember } = useScene();
  const [place, setPlace] = useState<ExplorePlace | undefined>(places[placeId]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setPlace(places[placeId]);
    setError("");
    repository
      .detail(placeId)
      .then((p) => {
        if (active) {
          setPlace(p);
          remember(p);
        }
      })
      .catch((e) => {
        if (active) setError(message(e));
      });
    return () => {
      active = false;
    };
  }, [placeId]);
  return { place, error };
}
function Place({ map = false }: { map?: boolean }) {
  const from = (useLocation().state as { from?: string } | null)?.from;
  const { place: p, error } = usePlace();
  const { scene, update } = useScene();
  const assistant = useTravelAssistant();
  const [favorite, setFavorite] = useState<boolean | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  useEffect(() => {
    if (!p) return;
    let active = true;
    fetch(`/api/v1/me/favorites/${p.id}`)
      .then(async (r) => {
        if (!r.ok) throw Error("收藏状态暂时无法读取");
        return r.json();
      })
      .then((s) => {
        if (active) setFavorite(s.is_favorite);
      })
      .catch((e) => {
        if (active) setSaveError(message(e));
      });
    return () => {
      active = false;
    };
  }, [p?.id]);
  async function toggle() {
    if (!p || favorite === null) return;
    setSaving(true);
    setSaveError("");
    try {
      await repository.favorite(p.id, !favorite);
      setFavorite(!favorite);
    } catch (e) {
      setSaveError(message(e));
    } finally {
      setSaving(false);
    }
  }
  return (
    <main className="rxp-page discovery-detail">
      <Back
        to={from || scene.returnTo}
        label={
          from === "/assistant"
            ? "返回对话"
            : from === "/nearby"
              ? "返回附近发现"
              : from?.startsWith("/drafts/")
                ? "返回草稿"
                : scene.returnTo === "/favorites"
                  ? "返回收藏"
                  : "返回探索"
        }
      />
      {error && (
        <State error title="地点信息读取失败">
          <p>{error}</p>
        </State>
      )}
      {!p && !error && <State busy title="正在读取地点" />}
      {p && (
        <>
          <div className="discovery-detail-heading">
            <span className="rxp-eyebrow">{p.city} · 高德地点信息</span>
            <h1>{p.name}</h1>
            <p>
              <MapPin size={17} />
              {p.address || "地址暂无"}
            </p>
          </div>
          <div className="discovery-detail-grid">
            <section>
              <PlaceGallery key={p.id} photos={p.photos} name={p.name} />
              <div className="discovery-detail-actions">
                <button
                  onClick={() => void toggle()}
                  disabled={saving || favorite === null}
                >
                  <Heart size={17} fill={favorite ? "currentColor" : "none"} />
                  {saving ? "保存中…" : favorite ? "已收藏" : "收藏地点"}
                </button>
                <Link to={`/places/${p.id}/map`} state={{ from }}>
                  <Map size={17} />
                  查看地图
                </Link>
                <Link
                  className="primary"
                  to={`/places/${p.id}/route`}
                  state={{ from }}
                >
                  <Navigation size={17} />
                  怎么去
                </Link>
                <button onClick={() => assistant.openAssistant({ place: p })}>
                  <Sparkles size={17} />
                  问问 AI
                </button>
              </div>
              {saveError && <p role="alert">{saveError}</p>}
              <div className="discovery-information">
                <h2>了解这个地方</h2>
                {p.experience && <section aria-label="核实的游览主题">
                  <p>{p.experience.summary}</p>
                  <p>{p.experience.attributes.join(" · ")}</p>
                  <details><summary>依据与仍需确认的信息</summary>
                    <p>{p.experience.scope}</p>
                    <p>出发前仍需确认：{p.experience.unknown.join("、")}。</p>
                    <a href={p.experience.source_url} target="_blank" rel="noreferrer">{p.experience.source_title} <ExternalLink size={14} /></a>
                    <small>核对于 {new Date(p.experience.reviewed_at).toLocaleDateString("zh-CN")}</small>
                  </details>
                </section>}
                <div className="discovery-facts">
                  <span>
                    <Star size={18} />
                    {p.rating == null ? "暂无评分" : `${p.rating} / 5`}
                  </span>
                  <span>
                    {p.reference_cost_yuan == null
                      ? "暂无参考消费"
                      : `参考消费 ¥${p.reference_cost_yuan}/人`}
                  </span>
                </div>
                <p>
                  {p.description
                    ? p.description
                        .replaceAll(";", " · ")
                        .replaceAll("|", " / ")
                    : "暂无可核实的详细介绍。"}
                </p>
                <p>
                  开放时间、门票、预约及实时营业状态暂无可靠信息，出发前请向地点确认。
                </p>
                <a href={p.source_url} target="_blank" rel="noreferrer">
                  查看高德原始信息 <ExternalLink size={14} />
                </a>
                <small>
                  查询时间：{new Date(p.retrieved_at).toLocaleString("zh-CN")}
                  。参考消费不代表当前报价。
                </small>
              </div>
            </section>
            <section>
              {map ? (
                <ExploreMap
                  center={p.location}
                  points={[{ point: p.location, label: p.name, id: p.id }]}
                  savedView={scene.maps[p.id]}
                  onViewChange={(view) =>
                    update({ maps: { ...scene.maps, [p.id]: view } })
                  }
                />
              ) : (
                <div className="discovery-place-visual">
                  <MapPin size={45} strokeWidth={1} />
                  <span>{p.city}</span>
                  <small>{p.photos.length ? '查看地点位置' : '暂无已核实的授权照片'}</small>
                  <Link to={`/places/${p.id}/map`} state={{ from }}>
                    在地图上看看 <ArrowRight size={15} />
                  </Link>
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </main>
  );
}
function Directions() {
  const from = (useLocation().state as { from?: string } | null)?.from;
  const { place: p, error } = usePlace();
  const { scene, update } = useScene();
  const { placeId = "" } = useParams();
  const params = new URLSearchParams(useLocation().search);
  const route: RouteState = scene.routes[placeId] ?? {
    originName: "",
    query: "",
    mode: params.get("mode") === "driving" ? "driving" : "walk",
  };
  const [candidates, setCandidates] = useState<ExplorePlace[]>([]);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [searching, setSearching] = useState(false);
  const latest = useRef(route);
  latest.current = route;
  function change(patch: Partial<RouteState>) {
    update({
      routes: { ...scene.routes, [placeId]: { ...latest.current, ...patch } },
    });
  }
  useEffect(() => {
    const origin = params.get("origin_place_id");
    if (origin && !route.origin)
      void repository
        .detail(origin)
        .then((o) => change({ origin: o.location, originName: o.name }))
        .catch((e) => setFailure(message(e)));
  }, [placeId]);
  async function find() {
    if (!p) return;
    setSearching(true);
    setFailure("");
    try {
      const result = await repository.search({
        city: p.city,
        q: route.query,
        category: "all",
      });
      setCandidates(result.items);
      if (!result.items.length) setFailure("没有找到起点，试试更具体的名称。");
    } catch (e) {
      setFailure(message(e));
    } finally {
      setSearching(false);
    }
  }
  async function calculate() {
    if (!p || !route.origin) return;
    setBusy(true);
    setFailure("");
    try {
      const result = await repository.route(p.id, route.origin, route.mode);
      const current = latest.current;
      if (
        current.mode === route.mode &&
        current.origin?.longitude === route.origin.longitude &&
        current.origin?.latitude === route.origin.latitude
      )
        change({ result });
    } catch (e) {
      setFailure(message(e));
    } finally {
      setBusy(false);
    }
  }
  const origin = (point: ExplorePoint, name: string) =>
    change({ origin: point, originName: name, result: undefined });
  return (
    <main className="rxp-page discovery-route">
      <div className="discovery-back">
        <Link
          className="rxp-back-link"
          to={`/places/${placeId}`}
          state={{ from }}
        >
          <ArrowLeft size={16} />
          返回地点
        </Link>
      </div>
      {error && (
        <State error title="地点读取失败">
          {error}
        </State>
      )}
      {!p && !error && <State busy title="正在准备路线" />}
      {p && (
        <>
          <span className="rxp-eyebrow">从这里出发</span>
          <h1>
            怎么去 <em>{p.name}</em>
          </h1>
          <div className="discovery-route-grid">
            <section className="discovery-route-controls">
              <h2>从哪里出发？</h2>
              <p>搜索{p.city}的地点，或点击地图选择起点。</p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void find();
                }}
              >
                <input
                  aria-label="路线起点"
                  placeholder="输入车站、酒店或地点名称"
                  value={route.query}
                  onChange={(e) => change({ query: e.target.value })}
                />
                <button disabled={searching || !route.query.trim()}>
                  {searching ? "查找中…" : "查找起点"}
                </button>
              </form>
              <div className="discovery-origin-results">
                {candidates.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => {
                      origin(c.location, c.name);
                      setCandidates([]);
                    }}
                  >
                    {c.name}
                    <small>{c.address}</small>
                  </button>
                ))}
              </div>
              {route.origin && (
                <p className="discovery-origin">
                  <Check size={16} />
                  {route.originName}
                </p>
              )}
              <label>
                出行方式
                <select
                  aria-label="出行方式"
                  value={route.mode}
                  onChange={(e) =>
                    change({
                      mode: e.target.value as "walk" | "driving",
                      result: undefined,
                    })
                  }
                >
                  <option value="walk">步行</option>
                  <option value="driving">驾车</option>
                </select>
              </label>
              <button
                className="rxp-primary-action"
                disabled={!route.origin || busy}
                onClick={() => void calculate()}
              >
                <Navigation size={17} />
                {busy ? "正在查询…" : "查询路线"}
              </button>
              {failure && <p role="alert">{failure}</p>}
              {route.result && (
                <div className="discovery-route-summary" role="status">
                  <h2>到 {p.name}</h2>
                  <strong>
                    {distance(route.result.distance_meters)} · 约
                    {Math.ceil(route.result.duration_seconds / 60)}分钟
                  </strong>
                  <p>
                    {route.originName} → {p.name}
                  </p>
                  <a
                    href={route.result.external_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    打开高德出发 <ExternalLink size={15} />
                  </a>
                  <small>高德路线估计 · 非实时导航</small>
                </div>
              )}
            </section>
            <ExploreMap
              center={p.location}
              points={[
                ...(route.origin
                  ? [{ point: route.origin, label: route.originName }]
                  : []),
                { point: p.location, label: p.name },
              ]}
              path={route.result?.path}
              pickMode
              onPickPoint={(point) => origin(point, "地图选定起点")}
              savedView={scene.maps[`route:${p.id}`]}
              onViewChange={(view) =>
                update({ maps: { ...scene.maps, [`route:${p.id}`]: view } })
              }
            />
          </div>
        </>
      )}
    </main>
  );
}
function Favorites() {
  const [places, setPlaces] = useState<ExplorePlace[]>();
  const [error, setError] = useState("");
  const { update } = useScene();
  useEffect(() => {
    const controller = new AbortController();
    repository
      .favorites(controller.signal)
      .then((r) => setPlaces(r.items))
      .catch((e) => {
        if (!controller.signal.aborted) setError(message(e));
      });
    return () => controller.abort();
  }, []);
  return (
    <main className="rxp-page">
      <Back to="/" />
      <span className="rxp-eyebrow">留住心动的地方</span>
      <h1>我的收藏</h1>
      {error ? (
        <State error title="收藏暂时无法读取">
          {error}
        </State>
      ) : !places ? (
        <State busy title="正在读取收藏" />
      ) : places.length ? (
        <div className="discovery-grid">
          {places.map((p) => (
            <Card
              key={p.id}
              place={p}
              onOpen={() => update({ returnTo: "/favorites" })}
            />
          ))}
        </div>
      ) : (
        <State title="还没有收藏地点">
          <p>浏览地点时点一下收藏，下次在这里找到它。</p>
          <Link to="/">
            去探索 <ArrowRight size={15} />
          </Link>
        </State>
      )}
    </main>
  );
}
function message(e: unknown) {
  return e instanceof Error ? e.message : "服务暂不可用，请稍后重试。";
}
function distance(m: number) {
  return m >= 1000 ? `${(m / 1000).toFixed(1)}公里` : `${Math.round(m)}米`;
}
