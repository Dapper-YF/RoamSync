import {
  ArrowLeft,
  ArrowRight,
  Bookmark,
  Check,
  ChevronDown,
  CircleHelp,
  Compass,
  ExternalLink,
  Heart,
  MapPin,
  MapPinned,
  MessageCircle,
  Navigation,
  Search,
  Sparkles,
  Star,
  Utensils,
  Hotel,
  Landmark,
  UserRound,
  Clock3,
  Route as RouteIcon,
  Info,
} from "lucide-react";
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { createExploreRepository } from "../data/exploreRepository";
import type { ExploreCategory, ExplorePlace, ExplorePoint, ExploreRepository, ExploreRoute, DiscoveryFilters } from "../domain/explore";
import { useTravelAssistant } from "./TravelAssistant";
import { ExploreMap } from "./ExploreMap";
import "./ProductExperience.css";
import { PreferencePanel } from "./PreferencePanel";

interface ProductLayoutProps { repository?: ExploreRepository }
interface ProductContext { repository: ExploreRepository }
interface CitySuggestion { name: string; adcode: string; citycode: string; coordinates: [number, number] }

const defaultRepository = createExploreRepository();
const CATEGORY_OPTIONS: Array<{ value: ExploreCategory; label: string; icon: typeof Compass }> = [
  { value: "all", label: "全部灵感", icon: Compass },
  { value: "sight", label: "看风景", icon: Landmark },
  { value: "food", label: "尝美食", icon: Utensils },
  { value: "hotel", label: "住一晚", icon: Hotel },
];
const CITY_THEME_OPTIONS: Array<{ label: string; query: string; category: ExploreCategory }> = [
  { label: "城市景点", query: "景点", category: "sight" },
  { label: "博物馆", query: "博物馆", category: "sight" },
  { label: "公园", query: "公园", category: "sight" },
  { label: "茶馆", query: "茶馆", category: "food" },
  { label: "当地美食", query: "当地美食", category: "food" },
];

export function ProductLayout({ repository: injectedRepository }: ProductLayoutProps) {
  const repository = useMemo(() => injectedRepository ?? defaultRepository, [injectedRepository]);
  const { openAssistant } = useTravelAssistant();
  const { pathname } = useLocation();
  useEffect(() => {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [pathname]);
  const tripMatch = pathname.match(/^\/trips\/([^/]+)(?:\/|$)/);
  const tripId = tripMatch?.[1] && tripMatch[1] !== "new" ? tripMatch[1] : undefined;
  const openAssistantForCurrentPage = () => openAssistant(tripId ? { tripId } : undefined);

  return (
    <div className="rxp-shell">
      <header className="rxp-header">
        <Link className="rxp-brand" to="/" aria-label="RoamSync 探索首页">
          <span className="rxp-brand-mark"><Compass size={19} strokeWidth={2.2} /></span>
          <span><strong>RoamSync</strong><small>TRAVEL, AT YOUR PACE</small></span>
        </Link>
        <nav className="rxp-nav" aria-label="主导航">
          <NavLink to="/" end className={({ isActive }) => `rxp-nav-link${isActive ? " is-active" : ""}`}>探索</NavLink>
          <NavLink to="/assistant" className={({ isActive }) => `rxp-nav-link${isActive ? " is-active" : ""}`}>助手</NavLink>
          <NavLink to="/drafts" className={({ isActive }) => `rxp-nav-link${isActive ? " is-active" : ""}`}>草稿</NavLink>
          <NavLink to="/trips" className={({ isActive }) => `rxp-nav-link${isActive ? " is-active" : ""}`}>旅程</NavLink>
          <NavLink to="/me" className={({ isActive }) => `rxp-nav-link${isActive ? " is-active" : ""}`}>我的</NavLink>
        </nav>
        <button className="rxp-assistant-button" type="button" onClick={openAssistantForCurrentPage}>
          <Sparkles size={16} /> <span>问问旅行助手</span>
        </button>
      </header>
      <div className="rxp-content"><Outlet context={{ repository } satisfies ProductContext} /></div>
      <button className="rxp-mobile-assistant" type="button" aria-label="打开旅行助手" onClick={openAssistantForCurrentPage}>
        <Sparkles size={19} />
      </button>
    </div>
  );
}

export function ExplorePage({ repository: injectedRepository }: ProductLayoutProps) {
  const repository = useProductRepository(injectedRepository);
  const [city, setCity] = useState("杭州");
  const [query, setQuery] = useState("景点");
  const [category, setCategory] = useState<ExploreCategory>("sight");
  const [citySuggestions, setCitySuggestions] = useState<CitySuggestion[]>([]);
  const [citySearching, setCitySearching] = useState(false);
  const [results, setResults] = useState<ExplorePlace[]>([]);
  const [source, setSource] = useState("");
  const [fetchedAt, setFetchedAt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [discoveryFilters, setDiscoveryFilters] = useState<DiscoveryFilters>({ include_unknown: true, use_preferences: true });
  const filtersRef = useRef(discoveryFilters); filtersRef.current = discoveryFilters;
  const [nearby, setNearby] = useState(false);
  const nearbyRef = useRef(nearby); nearbyRef.current = nearby;
  const [nearLng, setNearLng] = useState("");
  const [nearLat, setNearLat] = useState("");
  const [showPreferences, setShowPreferences] = useState(false);
  const searchController = useRef<AbortController | null>(null);
  const cityController = useRef<AbortController | null>(null);

  const loadCities = useCallback((keyword: string) => {
    cityController.current?.abort();
    const normalized = keyword.trim();
    if (normalized.length < 1) { setCitySuggestions([]); return; }
    const controller = new AbortController();
    cityController.current = controller;
    setCitySearching(true);
    void searchCities(normalized, controller.signal)
      .then(setCitySuggestions)
      .catch(() => { if (!controller.signal.aborted) setCitySuggestions([]); })
      .finally(() => { if (!controller.signal.aborted) setCitySearching(false); });
  }, []);

  const runSearch = useCallback(async (nextCity: string, nextQuery: string, nextCategory: ExploreCategory) => {
    if (nearbyRef.current && !filtersRef.current.center) { setError("请先确认附近搜索的GCJ02位置。"); return; }
    const cityName = nextCity.trim();
    if (!cityName) { setError("先写下想去的城市。"); return; }
    searchController.current?.abort();
    const controller = new AbortController();
    searchController.current = controller;
    setLoading(true);
    setError(null);
    setHasSearched(true);
    try {
      const cityMatches = await searchCities(cityName, controller.signal);
      if (controller.signal.aborted) return;
      const selected = cityMatches.find((item) => item.name === cityName) ?? cityMatches[0];
      if (!selected) throw new Error("没有找到这个城市，请试试附近更大的城市名称。");
      setCity(selected.name);
      setCitySuggestions([]);
      const input = { city: selected.name, q: nextQuery.trim() || undefined, category: nextCategory };
      const response = repository.discover ? await repository.discover(input, filtersRef.current, controller.signal) : await repository.search(input, controller.signal);
      if (controller.signal.aborted) return;
      setResults(response.items);
      setSource(response.source);
      setFetchedAt(response.fetched_at);
    } catch (cause) {
      if (!controller.signal.aborted) setError(toMessage(cause));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [repository]);

  useEffect(() => {
    void runSearch("杭州", "景点", "sight");
    return () => { searchController.current?.abort(); cityController.current?.abort(); };
  }, [runSearch]);

  const submit = (event: FormEvent) => { event.preventDefault(); void runSearch(city, query, category); };
  const chooseCity = (suggestion: CitySuggestion) => { setCity(suggestion.name); setCitySuggestions([]); };

  return (
    <main className="rxp-page rxp-explore-page">
      <section className="rxp-explore-hero">
        <div className="rxp-hero-copy">
          <span className="rxp-eyebrow"><span /> 走进城市，发现自己的路线</span>
          <h1>每一段旅程，<br /><em>从好奇开始。</em></h1>
          <p>找一个值得停留的地方。先看看，再慢慢决定下一站。</p>
        </div>
        <div className="rxp-hero-art" aria-hidden="true">
          <div className="rxp-art-sun" /><div className="rxp-art-hill rxp-art-hill-back" /><div className="rxp-art-hill rxp-art-hill-front" />
          <div className="rxp-art-path" /><div className="rxp-art-stamp">GO<br /><small>YOUR<br />OWN WAY</small></div>
          <span className="rxp-art-caption">a little further, a little slower</span>
        </div>
      </section>

      <section className="rxp-search-panel" aria-label="搜索目的地">
        <form className="rxp-search-form" onSubmit={submit}>
          <label className="rxp-city-field">
            <span>想去哪里</span>
            <span className="rxp-input-line"><MapPin size={17} /><input value={city} onChange={(event) => { setCity(event.target.value); loadCities(event.target.value); }} onFocus={() => { if (city.trim()) loadCities(city); }} aria-label="目的地城市" autoComplete="off" placeholder="输入城市名称" /></span>
            {citySuggestions.length > 0 && <div className="rxp-suggestions" role="listbox" aria-label="城市建议">{citySuggestions.map((item) => <button key={`${item.adcode}-${item.name}`} type="button" role="option" aria-selected="false" onClick={() => chooseCity(item)}><span>{item.name}</span><small>高德城市</small></button>)}</div>}
            {citySearching && citySuggestions.length === 0 && <div className="rxp-city-lookup-status" role="status">正在核对城市名称…</div>}
          </label>
          <label className="rxp-keyword-field">
            <span>想找什么</span>
            <span className="rxp-input-line"><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} aria-label="地点关键词" placeholder="例如：茶馆、江边、博物馆" /></span>
          </label>
          <button className="rxp-search-submit" type="submit" disabled={loading}><Search size={17} />{loading ? "正在寻找" : "开始探索"}</button>
        </form>
        <div className="rxp-category-row" role="group" aria-label="地点类别">
          {CATEGORY_OPTIONS.map(({ value, label, icon: Icon }) => <button key={value} type="button" className={category === value ? "is-selected" : ""} aria-pressed={category === value} onClick={() => { setCategory(value); void runSearch(city, query, value); }}><Icon size={15} />{label}</button>)}
          <span className="rxp-category-note"><Info size={13} />可查看地点来源与查询时间</span>
        </div>
        <details className="rxp-discovery-options"><summary>附近地点与筛选</summary>
          <p>附近搜索使用你明确选择的高德 GCJ-02 坐标；不会把城市中心当作你的当前位置。</p>
          <label><input type="checkbox" checked={nearby} onChange={event => { setNearby(event.target.checked); if (!event.target.checked) setDiscoveryFilters(current => ({ ...current, center: undefined })); }} />搜索所选位置附近</label>
          {nearby && <><ExploreMap center={{ longitude: Number(nearLng) || 120.15, latitude: Number(nearLat) || 30.25, coordinate_system: "gcj02" }} points={discoveryFilters.center ? [{ point: discoveryFilters.center, label: "附近搜索中心" }] : []} pickMode onPickPoint={point => { setNearLng(String(point.longitude)); setNearLat(String(point.latitude)); setDiscoveryFilters(current => ({ ...current, center: point })); }} ariaLabel="选择附近搜索中心" />
            <div className="rxp-filter-row"><label>经度 GCJ-02<input aria-label="附近经度" value={nearLng} onChange={event => { setNearLng(event.target.value); setDiscoveryFilters(current => ({ ...current, center: undefined })); }} /></label><label>纬度 GCJ-02<input aria-label="附近纬度" value={nearLat} onChange={event => { setNearLat(event.target.value); setDiscoveryFilters(current => ({ ...current, center: undefined })); }} /></label>
            <button type="button" onClick={() => { const longitude = Number(nearLng), latitude = Number(nearLat); if (!nearLng.trim() || !nearLat.trim() || !Number.isFinite(longitude) || !Number.isFinite(latitude) || Math.abs(longitude) > 180 || Math.abs(latitude) > 90) { setError("请填写有效的GCJ02经纬度。"); return; } setDiscoveryFilters(current => ({ ...current, center: { longitude, latitude, coordinate_system: "gcj02" } })); }}>确认附近位置</button></div>
            <label>范围<select aria-label="附近范围" value={discoveryFilters.radius ?? 3000} onChange={event => setDiscoveryFilters(current => ({ ...current, radius: Number(event.target.value) }))}><option value="1000">1公里</option><option value="3000">3公里</option><option value="5000">5公里</option></select></label>
            <p>{discoveryFilters.center ? `已选择GCJ02位置：${discoveryFilters.center.longitude.toFixed(5)}, ${discoveryFilters.center.latitude.toFixed(5)}` : "尚未确认附近中心，请先选点。"}</p></>}
          <div className="rxp-filter-row"><label>最低评分<select aria-label="最低评分" value={discoveryFilters.min_rating ?? ""} onChange={event => setDiscoveryFilters(current => ({ ...current, min_rating: event.target.value ? Number(event.target.value) : undefined }))}><option value="">不限</option><option value="4">4分</option><option value="4.5">4.5分</option></select></label>
          <label>餐饮人均参考价<select aria-label="餐饮人均参考价" value={discoveryFilters.max_food_price_yuan ?? ""} onChange={event => setDiscoveryFilters(current => ({ ...current, max_food_price_yuan: event.target.value ? Number(event.target.value) : undefined }))}><option value="">不限</option><option value="50">50元以内</option><option value="100">100元以内</option><option value="200">200元以内</option></select></label>
          <label><input type="checkbox" checked={discoveryFilters.include_unknown ?? true} onChange={event => setDiscoveryFilters(current => ({ ...current, include_unknown: event.target.checked }))} />保留评分或餐饮参考价未知地点</label></div>
          <label><input type="checkbox" checked={discoveryFilters.use_preferences ?? true} onChange={event => setDiscoveryFilters(current => ({ ...current, use_preferences: event.target.checked }))} />使用我明确保存的探索偏好</label>
          <p>酒店仅支持地点浏览，实时房价与库存不支持。筛选仅作用于本次供应商返回的地点。</p>
          <button className="rxp-secondary-action" disabled={loading || (nearby && !discoveryFilters.center)} type="button" onClick={() => void runSearch(city, query, category)}>应用筛选</button>
        </details>
        <div className="rxp-filter-row" aria-label="城市探索主题">{CITY_THEME_OPTIONS.map(({ label, query: theme, category: themeCategory }) => <button className="rxp-secondary-action" type="button" key={label} onClick={() => { setQuery(theme); setCategory(themeCategory); void runSearch(city, theme, themeCategory); }}>{label}</button>)}</div>
        <button className="rxp-preference-toggle" type="button" onClick={() => setShowPreferences(value => !value)}>设置我的探索偏好</button>
        {showPreferences && <PreferencePanel onSaved={() => void runSearch(city, query, category)} />}
      </section>

      <section className="rxp-results-section" aria-live="polite">
        <div className="rxp-section-heading">
          <div><span className="rxp-eyebrow">THE CITY, IN YOUR OWN WAY</span><h2>{city || "目的地"}<span> · 地点探索</span></h2></div>
          {hasSearched && !loading && !error && <div className="rxp-result-meta"><strong>{results.length}</strong> 个地点{source && <span> · {source}</span>}</div>}
        </div>
        {loading && <div className="rxp-state-card" role="status"><span className="rxp-spinner" />正在为你找真实地点…</div>}
        {!loading && error && <div className="rxp-state-card rxp-error-state" role="alert"><CircleHelp size={22} /><div><strong>这次没能找到结果</strong><p>{error}</p><button type="button" onClick={() => void runSearch(city, query, category)}>再试一次 <ArrowRight size={14} /></button></div></div>}
        {!loading && !error && results.length > 0 && <div className="rxp-place-grid">{results.map((place, index) => <PlaceCard key={place.id} place={place} index={index} />)}</div>}
        {!loading && !error && hasSearched && results.length === 0 && <div className="rxp-state-card rxp-empty-state"><Compass size={24} /><div><strong>这次没有搜到地点</strong><p>换个关键词或类别，再看看城市的另一面。</p></div></div>}
        {!loading && fetchedAt && results.length > 0 && <p className="rxp-data-note">信息查询于 {formatDateTime(fetchedAt)} · 评分与参考价格仅在数据源提供时展示。</p>}
      </section>
    </main>
  );
}

export function PlaceDetailPage({ repository: injectedRepository }: ProductLayoutProps) {
  const repository = useProductRepository(injectedRepository);
  const { placeId = "" } = useParams();
  const { openAssistant } = useTravelAssistant();
  const [place, setPlace] = useState<ExplorePlace | null>(null);
  const [loading, setLoading] = useState(true);
  const [favoriteBusy, setFavoriteBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError(null); setPlace(null);
    Promise.all([
      repository.detail(placeId, controller.signal),
      repository.favorites(controller.signal).catch(() => null),
    ]).then(([detail, favorites]) => {
      if (controller.signal.aborted) return;
      const isSaved = favorites ? favorites.items.some((item) => item.id === detail.id) : detail.favorite;
      setPlace({ ...detail, favorite: isSaved });
    }).catch((cause: unknown) => { if (!controller.signal.aborted) setError(toMessage(cause)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [placeId, repository]);

  const toggleFavorite = async () => {
    if (!place || favoriteBusy) return;
    const value = !place.favorite;
    setFavoriteBusy(true); setError(null);
    try { await repository.favorite(place.id, value); setPlace({ ...place, favorite: value }); }
    catch (cause) { setError(toMessage(cause)); }
    finally { setFavoriteBusy(false); }
  };

  if (loading) return <ProductLoading label="正在打开地点" />;
  if (!place) return <ProductFailure title="暂时无法打开这个地点" message={error ?? "请返回探索页重新选择。"} />;
  const cover = place.photos[0];
  return (
    <main className="rxp-page rxp-detail-page">
      <Link className="rxp-back-link" to="/"><ArrowLeft size={15} />回到探索</Link>
      <div className="rxp-detail-layout">
        <section className="rxp-detail-main">
          <PhotoFrame photo={cover} title={place.name} className="rxp-detail-cover" />
          {place.image_status === "withheld_pending_license" && <p className="rxp-data-note">图片使用授权尚未核验，暂不展示。</p>}
          {place.identity_status && place.identity_status !== "provider_identity" && <p className="rxp-data-note" role="status">地点身份暂未得到数据源重新确认，资料可能已过期。</p>}
          {place.photos.length > 1 && <div className="rxp-photo-strip">{place.photos.slice(1).map((photo) => <a href={photo.source_url} key={photo.url} target="_blank" rel="noreferrer" aria-label={`查看${photo.title || place.name}照片来源`}><img src={photo.url} alt={photo.title || place.name} loading="lazy" /><ExternalLink size={13} /></a>)}</div>}
          <div className="rxp-detail-copy">
            <span className="rxp-category-label"><CategoryIcon category={place.category} />{categoryName(place.category)} <i>·</i> {place.city}</span>
            <h1>{place.name}</h1>
            <p className="rxp-address"><MapPin size={15} />{place.address || "地址暂缺"}</p>
            {place.description ? <p className="rxp-description">{place.description}</p> : <p className="rxp-description rxp-unknown">暂时没有地点介绍。</p>}
            <div className="rxp-facts-row"><Fact icon={<Star size={16} />} label="评分" value={place.rating == null ? "暂无评分" : place.rating.toFixed(1)} /><Fact icon={<Bookmark size={16} />} label="参考消费" value={formatPlaceCost(place)} /><Fact icon={<MapPinned size={16} />} label="坐标" value="高德坐标 · GCJ-02" /></div>
            <div className="rxp-source-box"><div><span>地点信息来源</span><small>查询于 {formatDateTime(place.retrieved_at)}</small></div><a href={place.source_url} target="_blank" rel="noreferrer">查看来源 <ExternalLink size={13} /></a></div>
            {error && <p className="rxp-inline-error" role="alert">{error}</p>}
          </div>
          {place.photos.length > 0 && <div className="rxp-attributions"><strong>照片来源</strong>{place.photos.map((photo) => <a key={`${photo.url}-${photo.attribution}`} href={photo.source_url} target="_blank" rel="noreferrer">{photo.attribution || photo.title || "查看原始照片"}<ExternalLink size={12} /></a>)}</div>}
        </section>
        <aside className="rxp-detail-aside">
          <div className="rxp-action-card"><span className="rxp-eyebrow">MAKE IT YOURS</span><h2>把喜欢的地方，<br />留给下一次出发。</h2>
            <button className={`rxp-primary-action${place.favorite ? " is-saved" : ""}`} type="button" disabled={favoriteBusy} onClick={() => void toggleFavorite()}>{place.favorite ? <Check size={17} /> : <Heart size={17} />}{favoriteBusy ? "正在保存" : place.favorite ? "已收藏" : "收藏这个地点"}</button>
            <button className="rxp-secondary-action" type="button" onClick={() => openAssistant({ place, prompt: `帮我了解${place.name}，适合怎么安排？` })}><MessageCircle size={17} />问问这里</button>
            <div className="rxp-action-links"><Link to={`/places/${encodeURIComponent(place.id)}/map`}><MapPinned size={16} />在地图上看<ArrowRight size={14} /></Link><Link to={`/places/${encodeURIComponent(place.id)}/route`}><RouteIcon size={16} />规划怎么去<ArrowRight size={14} /></Link></div>
            <p className="rxp-honesty-note"><Info size={14} />只显示数据源提供的信息；没有的内容会明确标出。</p>
          </div>
        </aside>
      </div>
    </main>
  );
}

export function FavoritesPage({ repository: injectedRepository }: ProductLayoutProps) {
  const repository = useProductRepository(injectedRepository);
  const [items, setItems] = useState<ExplorePlace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError(null);
    try { setItems((await repository.favorites(signal)).items); }
    catch (cause) { if (!signal?.aborted) setError(toMessage(cause)); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [repository]);
  useEffect(() => { const controller = new AbortController(); void reload(controller.signal); return () => controller.abort(); }, [reload]);

  const removeFavorite = async (place: ExplorePlace) => {
    try { await repository.favorite(place.id, false); setItems((current) => current.filter((item) => item.id !== place.id)); }
    catch (cause) { setError(toMessage(cause)); }
  };

  return <main className="rxp-page rxp-collection-page">
    <section className="rxp-page-heading"><span className="rxp-eyebrow">YOUR SAVED PLACES</span><h1>喜欢的地方，<em>都在这里。</em></h1><p>收藏会保存在 RoamSync 收藏列表中，之后可以回来继续看。</p></section>
    {loading && <ProductLoading label="正在读取收藏" compact />}
    {!loading && error && <ProductFailure title="暂时无法读取收藏" message={error} onRetry={() => void reload()} />}
    {!loading && !error && items.length === 0 && <div className="rxp-collection-empty"><span><Heart size={23} /></span><h2>这里还空着</h2><p>发现一个喜欢的地方，打开它并点下收藏。</p><Link className="rxp-primary-action" to="/"><Compass size={16} />去探索</Link></div>}
    {!loading && !error && items.length > 0 && <div className="rxp-place-grid">{items.map((place, index) => <PlaceCard key={place.id} place={place} index={index} onRemove={() => void removeFavorite(place)} />)}</div>}
  </main>;
}

export function MyPage() {
  return <main className="rxp-page rxp-profile-page">
    <section className="rxp-page-heading"><span className="rxp-eyebrow">A SPACE FOR YOUR JOURNEYS</span><h1>给旅程留一点<em>自己的节奏。</em></h1><p>收藏喜欢的地点，在每趟旅程里慢慢安排。</p></section>
    <div className="rxp-profile-grid">
      <Link className="rxp-profile-card" to="/favorites"><span className="rxp-profile-icon"><Heart size={20} /></span><small>COLLECTION</small><h2>我的收藏</h2><p>回到你留意过的真实地点。</p><ArrowRight size={17} /></Link>
      <Link className="rxp-profile-card" to="/trips"><span className="rxp-profile-icon is-orange"><Compass size={20} /></span><small>YOUR JOURNEYS</small><h2>我的旅程</h2><p>查看行程，或开始规划一趟新的旅行。</p><ArrowRight size={17} /></Link>
      <article className="rxp-profile-card rxp-preference-card"><span className="rxp-profile-icon is-blue"><UserRound size={20} /></span><small>PREFERENCES</small><h2>旅行偏好</h2><PreferencePanel /></article>
    </div>
    <p className="rxp-profile-footnote"><Info size={14} />探索偏好独立保存；正式旅程的节奏、交通等设置仍保存在各自旅程中。</p>
  </main>;
}

export function PlaceMapPage({ repository: injectedRepository }: ProductLayoutProps) {
  const repository = useProductRepository(injectedRepository);
  const { placeId = "" } = useParams();
  const [place, setPlace] = useState<ExplorePlace | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { const controller = new AbortController(); repository.detail(placeId, controller.signal).then(setPlace).catch((cause: unknown) => { if (!controller.signal.aborted) setError(toMessage(cause)); }).finally(() => { if (!controller.signal.aborted) setLoading(false); }); return () => controller.abort(); }, [placeId, repository]);
  if (loading) return <ProductLoading label="正在准备地图" />;
  if (!place) return <ProductFailure title="无法显示地点地图" message={error ?? "请回到探索页重新打开。"} />;
  const amapUrl = `https://uri.amap.com/marker?position=${place.location.longitude},${place.location.latitude}&name=${encodeURIComponent(place.name)}`;
  return <main className="rxp-page rxp-map-page">
    <Link className="rxp-back-link" to={`/places/${encodeURIComponent(place.id)}`}><ArrowLeft size={15} />返回地点</Link>
    <div className="rxp-map-heading"><div><span className="rxp-eyebrow">A PLACE ON THE MAP</span><h1>{place.name}</h1><p><MapPin size={14} />{place.address || place.city}</p></div><a className="rxp-secondary-action" href={amapUrl} target="_blank" rel="noreferrer">在高德地图打开 <ExternalLink size={14} /></a></div>
    <ExploreMap center={place.location} points={[{ point: place.location, label: place.name }]} ariaLabel={`${place.name}地图`} />
    <p className="rxp-map-caption"><Info size={14} />地图由高德提供；地点坐标为 GCJ-02。{place.freshness === "stale" && " 当前地点资料为上次查询结果。"}</p>
  </main>;
}

export function RoutePage({ repository: injectedRepository }: ProductLayoutProps) {
  const [routeParams] = useSearchParams();
  const originPlaceId = routeParams.get("origin_place_id");
  const requestedMode = routeParams.get("mode") === "driving" ? "driving" : "walk";
  const repository = useProductRepository(injectedRepository);
  const { placeId = "" } = useParams();
  const [place, setPlace] = useState<ExplorePlace | null>(null);
  const [loadingPlace, setLoadingPlace] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [longitude, setLongitude] = useState("");
  const [latitude, setLatitude] = useState("");
  const [origin, setOrigin] = useState<ExplorePoint | null>(null);
  const [originCityQuery, setOriginCityQuery] = useState("");
  const [originPlaceQuery, setOriginPlaceQuery] = useState("");
  const [originCandidates, setOriginCandidates] = useState<ExplorePlace[]>([]);
  const [originSearching, setOriginSearching] = useState(false);
  const [citySuggestions, setCitySuggestions] = useState<CitySuggestion[]>([]);
  const [mode, setMode] = useState<ExploreRoute["mode"]>(repository.routeModes?.[0] ?? "transit");
  const [route, setRoute] = useState<ExploreRoute | null>(null);
  const [routeLoading, setRouteLoading] = useState(false);
  const cityController = useRef<AbortController | null>(null);

  useEffect(() => { const controller = new AbortController(); repository.detail(placeId, controller.signal).then(setPlace).catch((cause: unknown) => { if (!controller.signal.aborted) setPageError(toMessage(cause)); }).finally(() => { if (!controller.signal.aborted) setLoadingPlace(false); }); return () => controller.abort(); }, [placeId, repository]);

  useEffect(() => {
    if (!place || !originPlaceId) return;
    let cancelled = false;
    setRouteLoading(true); setPageError(null);
    (async () => {
      const from = await repository.detail(originPlaceId);
      if (cancelled) return;
      setOrigin(from.location); setLongitude(String(from.location.longitude)); setLatitude(String(from.location.latitude));
      setOriginCityQuery(from.name); setMode(requestedMode);
      const next = await repository.route(place.id, from.location, requestedMode);
      if (!cancelled) setRoute(next);
    })().catch((cause) => { if (!cancelled) setPageError(toMessage(cause)); })
      .finally(() => { if (!cancelled) setRouteLoading(false); });
    return () => { cancelled = true; };
  }, [originPlaceId, place, repository, requestedMode]);

  const updateOrigin = (point: ExplorePoint | null, label?: string) => {
    setOrigin(point); setRoute(null);
    setLongitude(point ? point.longitude.toFixed(6) : "");
    setLatitude(point ? point.latitude.toFixed(6) : "");
    if (label) setOriginCityQuery(label);
  };
  const searchOriginCity = (query: string) => {
    setOriginCityQuery(query);
    cityController.current?.abort();
    if (!query.trim()) { setCitySuggestions([]); return; }
    const controller = new AbortController(); cityController.current = controller;
    void searchCities(query, controller.signal).then((suggestions) => { if (!controller.signal.aborted) setCitySuggestions(suggestions); }).catch(() => { if (!controller.signal.aborted) setCitySuggestions([]); });
  };
  const chooseOriginCity = (city: CitySuggestion) => {
    setCitySuggestions([]);
    updateOrigin({ longitude: city.coordinates[0], latitude: city.coordinates[1], coordinate_system: "gcj02" }, city.name);
  };
  const updateManualOrigin = (lng: string, lat: string) => {
    setLongitude(lng); setLatitude(lat); setRoute(null);
    const parsedLng = Number(lng); const parsedLat = Number(lat);
    const valid = lng.trim() !== "" && lat.trim() !== "" && Number.isFinite(parsedLng) && Number.isFinite(parsedLat) && parsedLng >= -180 && parsedLng <= 180 && parsedLat >= -90 && parsedLat <= 90;
    setOrigin(valid ? { longitude: parsedLng, latitude: parsedLat, coordinate_system: "gcj02" } : null);
  };
  const getRoute = async () => {
    if (!place || !origin) { setPageError("先在地图上点选起点，选择城市中心，或填写完整的 GCJ-02 坐标。"); return; }
    setRouteLoading(true); setPageError(null); setRoute(null);
    try { setRoute(await repository.route(place.id, origin, mode)); }
    catch (cause) { setPageError(toMessage(cause)); }
    finally { setRouteLoading(false); }
  };

  if (loadingPlace) return <ProductLoading label="正在准备路线" />;
  if (!place) return <ProductFailure title="暂时无法规划路线" message={pageError ?? "请回到探索页重新打开地点。"} />;
  return <main className="rxp-page rxp-route-page">
    <Link className="rxp-back-link" to={`/places/${encodeURIComponent(place.id)}`}><ArrowLeft size={15} />返回地点</Link>
    <div className="rxp-route-title"><span className="rxp-eyebrow">FROM SOMEWHERE TO HERE</span><h1>怎么去 <em>{place.name}</em></h1><p>选一个出发点，我们会按高德返回的路线为你计算距离与用时。</p></div>
    <div className="rxp-route-layout">
      <section className="rxp-route-map-column">
        <ExploreMap center={place.location} points={origin ? [{ point: origin, label: "起点" }, { point: place.location, label: place.name }] : [{ point: place.location, label: place.name }]} pickMode onPickPoint={(point) => { updateOrigin(point); setOriginCityQuery("地图选点"); }} path={route?.path} ariaLabel="选择路线起点和查看路线" />
        <div className="rxp-map-caption"><MapPin size={14} /><span>点击地图选择起点。地图坐标使用 GCJ-02；设备定位不会自动填入。</span></div>
      </section>
      <section className="rxp-route-panel">
        <span className="rxp-step-number">01 <i>起点</i></span>
        <label className="rxp-origin-city"><span>搜索真实出发地点（当前目的地城市）</span><input aria-label="出发地点关键词" value={originPlaceQuery} onChange={event => setOriginPlaceQuery(event.target.value)} placeholder="例如：杭州东站" /></label>
        <button type="button" className="rxp-secondary-action" disabled={originSearching || !originPlaceQuery.trim()} onClick={() => { setOriginSearching(true); setPageError(null); void repository.search({ city: place.city, q: originPlaceQuery.trim(), category: "all" }).then(result => { setOriginCandidates(result.items); if (!result.items.length) setPageError("没有找到出发地点，请换一个关键词。"); }).catch(cause => setPageError(toMessage(cause))).finally(() => setOriginSearching(false)); }}>{originSearching ? "正在搜索" : "搜索出发地点"}</button>
        <div className="rxp-origin-candidates">{originCandidates.map(candidate => <button type="button" className="rxp-secondary-action" key={candidate.id} onClick={() => { updateOrigin(candidate.location, candidate.name); setOriginCandidates([]); }}><MapPin size={14} />{candidate.name} · {candidate.address || candidate.city}</button>)}</div>
        <label className="rxp-origin-city"><span>或选择出发城市中心（非当前位置）</span><span className="rxp-input-line"><Search size={16} /><input value={originCityQuery} onChange={(event) => searchOriginCity(event.target.value)} placeholder="例如：上海" autoComplete="off" /></span>
          {citySuggestions.length > 0 && <div className="rxp-suggestions" role="listbox" aria-label="起点城市建议">{citySuggestions.map((city) => <button key={`${city.adcode}-${city.name}`} type="button" role="option" onClick={() => chooseOriginCity(city)}><span>{city.name}</span><small>使用城市中心</small></button>)}</div>}
        </label>
        <div className="rxp-manual-coordinates"><span>或填写坐标 <b>GCJ-02 · 高德坐标</b></span><div><label>经度<input aria-label="起点经度 GCJ-02" inputMode="decimal" value={longitude} onChange={(event) => updateManualOrigin(event.target.value, latitude)} placeholder="120.xxxxxx" /></label><label>纬度<input aria-label="起点纬度 GCJ-02" inputMode="decimal" value={latitude} onChange={(event) => updateManualOrigin(longitude, event.target.value)} placeholder="30.xxxxxx" /></label></div></div>
        {origin && <div className="rxp-origin-confirmed"><Check size={15} /><span>起点已设置</span><code>{origin.longitude.toFixed(5)}, {origin.latitude.toFixed(5)}</code></div>}
        <label className="rxp-mode-select"><span className="rxp-step-number">02 <i>出行方式</i></span><span className="rxp-select-wrap"><select aria-label="出行方式" value={mode} onChange={(event) => { setMode(event.target.value as ExploreRoute["mode"]); setRoute(null); }}>{(!repository.routeModes || repository.routeModes.includes("transit")) && <option value="transit">公共交通</option>}<option value="driving">驾车</option><option value="walk">步行</option></select><ChevronDown size={15} /></span></label>
        {pageError && <p className="rxp-inline-error" role="alert">{pageError}</p>}
        <button className="rxp-primary-action rxp-route-submit" type="button" disabled={!origin || routeLoading} onClick={() => void getRoute()}>{routeLoading ? <span className="rxp-spinner rxp-spinner-light" /> : <Navigation size={16} />}{routeLoading ? "正在计算路线" : "查询真实路线"}</button>
        {route && <RouteSummary route={route} />}
        <p className="rxp-route-disclaimer"><Info size={14} />路线与用时来自服务查询，仅作出行参考。</p>
      </section>
    </div>
  </main>;
}

function RouteSummary({ route }: { route: ExploreRoute }) {
  return <div className="rxp-route-summary" role="status"><div className="rxp-route-summary-head"><span><Check size={14} />路线已返回</span><small>{route.provider}</small></div><div className="rxp-route-stats"><div><RouteIcon size={15} /><span>距离</span><strong>{formatDistance(route.distance_meters)}</strong></div><div><Clock3 size={15} /><span>预计用时</span><strong>{formatDuration(route.duration_seconds)}</strong></div></div><a href={route.external_url} target="_blank" rel="noreferrer">交给高德导航 <ExternalLink size={14} /></a></div>;
}

function PlaceCard({ place, index, onRemove }: { place: ExplorePlace; index: number; onRemove?: () => void }) {
  return <article className={`rxp-place-card rxp-card-tone-${index % 4}`}>
    <Link className="rxp-place-card-main" to={`/places/${encodeURIComponent(place.id)}`}>
      <PhotoFrame photo={place.photos[0]} title={place.name} className="rxp-place-card-photo" showCreditLink={false} />
      <div className="rxp-place-card-body"><span className="rxp-category-label"><CategoryIcon category={place.category} />{categoryName(place.category)} <i>·</i> {place.city}</span><h3>{place.name}</h3>{place.recommendation_reasons?.map(reason => <p className="rxp-recommendation-reason" key={reason}>{reason}</p>)}<p className="rxp-place-address"><MapPin size={13} />{place.address || "地址暂缺"}</p><div className="rxp-card-facts"><span><Star size={13} />{place.rating == null ? "暂无评分" : place.rating.toFixed(1)}</span><span>{formatPlaceCost(place)}</span></div></div>
    </Link>
    {onRemove && <button className="rxp-remove-favorite" type="button" aria-label={`取消收藏${place.name}`} onClick={onRemove}><Heart size={16} fill="currentColor" />取消收藏</button>}
    <div className="rxp-card-source"><span>{place.freshness === "stale" ? "上次查询" : "地点信息"} · {place.provider}</span><a href={place.source_url} target="_blank" rel="noreferrer" aria-label={`查看${place.name}信息来源`}><ExternalLink size={13} /></a></div>
  </article>;
}

function PhotoFrame({ photo, title, className = "", showCreditLink = true }: { photo?: ExplorePlace["photos"][number]; title: string; className?: string; showCreditLink?: boolean }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [photo?.url]);
  return <div className={`rxp-photo-frame ${className}`}>
    {photo && !failed ? <><img src={photo.url} alt={photo.title || title} loading="lazy" onError={() => setFailed(true)} />{photo.attribution && (showCreditLink ? <a className="rxp-photo-credit" href={photo.source_url} target="_blank" rel="noreferrer">{photo.attribution}</a> : <span className="rxp-photo-credit">{photo.attribution}</span>)}</> : <div className="rxp-photo-empty"><span><MapPin size={20} /></span><small>暂无可用照片</small></div>}
  </div>;
}

function Fact({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return <div className="rxp-fact"><span>{icon}</span><small>{label}</small><strong>{value}</strong></div>;
}

function CategoryIcon({ category }: { category: ExplorePlace["category"] }) {
  if (category === "food") return <Utensils size={13} />;
  if (category === "hotel") return <Hotel size={13} />;
  return <Landmark size={13} />;
}

function ProductLoading({ label, compact = false }: { label: string; compact?: boolean }) {
  return <div className={`rxp-standalone-state${compact ? " is-compact" : ""}`} role="status"><span className="rxp-spinner" />{label}…</div>;
}

function ProductFailure({ title, message, onRetry }: { title: string; message: string; onRetry?: () => void }) {
  return <div className="rxp-page rxp-failure-page"><Link className="rxp-back-link" to="/"><ArrowLeft size={15} />回到探索</Link><div className="rxp-state-card rxp-error-state" role="alert"><CircleHelp size={22} /><div><strong>{title}</strong><p>{message}</p>{onRetry && <button type="button" onClick={onRetry}>再试一次 <ArrowRight size={14} /></button>}</div></div></div>;
}

function useProductRepository(injected?: ExploreRepository) {
  const context = useOutletContext<ProductContext | null>();
  return injected ?? context?.repository ?? defaultRepository;
}

async function searchCities(keyword: string, signal?: AbortSignal): Promise<CitySuggestion[]> {
  const response = await fetch(`/api/v1/locations/cities?${new URLSearchParams({ keyword })}`, { signal });
  if (!response.ok) throw new Error("城市查询暂时不可用，请稍后重试。");
  const items = await response.json() as Array<{ name: string; adcode: string; citycode: string; longitude: number; latitude: number }>;
  return items.filter((item) => item.name && Number.isFinite(item.longitude) && Number.isFinite(item.latitude)).map((item) => ({ name: item.name, adcode: item.adcode, citycode: item.citycode, coordinates: [item.longitude, item.latitude] }));
}

function categoryName(category: ExplorePlace["category"]): string {
  return category === "sight" ? "风景名胜" : category === "food" ? "餐饮美食" : category === "hotel" ? "住宿" : "地点";
}
function formatPlaceCost(place: ExplorePlace): string {
  if (place.price_status !== "reference" || place.reference_cost_yuan == null) return "暂无参考价";
  return `¥${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(place.reference_cost_yuan)} 参考消费`;
}
function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "时间未知" : new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}
function formatDistance(meters: number): string {
  return meters >= 1000 ? `${(meters / 1000).toFixed(meters >= 10000 ? 0 : 1)} 公里` : `${Math.round(meters)} 米`;
}
function formatDuration(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60));
  return minutes >= 60 ? `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分` : `${minutes} 分钟`;
}
function toMessage(cause: unknown): string { return cause instanceof Error ? cause.message : "暂时无法完成请求，请稍后再试。"; }
