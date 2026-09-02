import {
  ArrowLeft,
  Archive,
  BedDouble,
  CalendarDays,
  Compass,
  Copy,
  MapPin,
  Pencil,
  Plus,
  Route as RouteIcon,
  Settings2,
  Sparkles,
  Trash2,
  WalletCards,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { Inspector } from "./components/Inspector";
import { AiPlannerPanel } from "./components/AiPlannerPanel";
import { MapCanvas } from "./components/MapCanvas";
import { PlacesDrawer } from "./components/PlacesDrawer";
import { PlannerSidebar } from "./components/PlannerSidebar";
import { TripBriefingDrawer } from "./components/TripBriefingDrawer";
import { ApiTripPlanningRepository } from "./data/apiTripPlanningRepository";
import { LocalTripPlanningRepository } from "./data/mockTripPlanningRepository";
import type {
  AccommodationPoi,
  Activity,
  ActivityUpdateInput,
  CitySuggestion,
  DayPlan,
  PlaceCandidate,
  PlaceOption,
  PlaceSearchResult,
  PlaceCategory,
  PlanningBudget,
  InterestCategory,
  PreferenceTransportMode,
  TripPace,
  RouteLeg,
  Trip,
  TripPlanningRepository,
} from "./domain/types";
import { formatFen } from "./utils/planner";

const INTEREST_OPTIONS: Array<{ value: InterestCategory; label: string }> = [
  { value: "history", label: "历史" },
  { value: "culture", label: "人文" },
  { value: "nature", label: "自然" },
  { value: "food", label: "美食" },
  { value: "photography", label: "摄影" },
  { value: "shopping", label: "购物" },
  { value: "family", label: "亲子" },
  { value: "nightlife", label: "夜游" },
];

const TRANSPORT_OPTIONS: Array<{ value: PreferenceTransportMode; label: string }> = [
  { value: "walk", label: "步行" },
  { value: "transit", label: "公交" },
  { value: "driving", label: "驾车" },
];

export function App({ repository: injectedRepository }: { repository?: TripPlanningRepository }) {
  const repository = useMemo(
    () => injectedRepository ?? (import.meta.env.VITE_USE_MOCK_REPOSITORY === "true" ? new LocalTripPlanningRepository() : new ApiTripPlanningRepository()),
    [injectedRepository],
  );
  return (
    <Routes>
      {!injectedRepository && <Route path="/demo" element={<Navigate to="/trips/00000000-0000-4000-8000-000000000001/planner" replace />} />}
      {!injectedRepository && <Route path="/trips/demo/planner" element={<Navigate to="/trips/00000000-0000-4000-8000-000000000001/planner" replace />} />}
      <Route path="/trips" element={<TripListPage repository={repository} />} />
      <Route path="/trips/new" element={<CreateTripPage repository={repository} />} />
      <Route path="/trips/:tripId/edit" element={<CreateTripPage repository={repository} />} />
      <Route path="/trips/:tripId/planner" element={<PlannerPage repository={repository} />} />
      <Route path="*" element={<Navigate to="/trips" replace />} />
    </Routes>
  );
}

function TripListPage({ repository }: { repository: TripPlanningRepository }) {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | NonNullable<Trip["status"]>>("all");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ trip: Trip; dayPlans: number; activities: number; candidates: number; expenses: number } | null>(null);
  const loadTrips = useCallback(async () => {
    try { setTrips(await repository.listTrips()); setError(null); }
    catch (cause) { setError(toOperationMessage(cause)); }
    finally { setLoading(false); }
  }, [repository]);
  useEffect(() => { void loadTrips(); }, [loadTrips]);
  const filteredTrips = trips.filter((trip) => {
    const matchesStatus = statusFilter === "all" || trip.status === statusFilter;
    const normalized = query.trim().toLocaleLowerCase();
    return matchesStatus && (!normalized || `${trip.title} ${trip.destination} ${trip.accommodation}`.toLocaleLowerCase().includes(normalized));
  });
  const runAction = async (tripId: string, action: "duplicate" | "archive") => {
    setBusyId(tripId); setError(null);
    try { if (action === "duplicate") await repository.duplicateTrip(tripId); else await repository.archiveTrip(tripId); await loadTrips(); }
    catch (cause) { setError(toOperationMessage(cause)); }
    finally { setBusyId(null); }
  };
  const prepareDelete = async (trip: Trip) => {
    setBusyId(trip.id); setError(null);
    try { const preview = await repository.getTripDeletionPreview(trip.id); setDeleteTarget({ trip, ...preview }); }
    catch (cause) { setError(toOperationMessage(cause)); }
    finally { setBusyId(null); }
  };
  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setBusyId(deleteTarget.trip.id);
    try { await repository.deleteTrip(deleteTarget.trip.id); setDeleteTarget(null); await loadTrips(); }
    catch (cause) { setError(toOperationMessage(cause)); }
    finally { setBusyId(null); }
  };
  return (
    <main className="directory-page">
      <header className="directory-header">
        <div className="brand-lockup dark"><span className="brand-mark"><Compass size={19} /></span><strong>RoamSync</strong><i>TRIPS</i></div>
        <Link className="primary-link" to="/trips/new"><Plus size={16} />创建旅行</Link>
      </header>
      <section className="directory-content">
        <div className="directory-title"><span className="eyebrow">YOUR JOURNEYS</span><h1>从一座城市开始规划</h1><p>行程、住宿、路线与预算将保存到 PostgreSQL。</p></div>
        <div className="directory-tools"><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索旅行或城市" aria-label="搜索旅行" /><div className="status-filters">{(["all", "upcoming", "active", "completed", "archived"] as const).map((status) => <button type="button" key={status} className={statusFilter === status ? "is-active" : ""} onClick={() => setStatusFilter(status)}>{statusLabel(status)}</button>)}</div></div>
        {loading ? <div className="directory-state"><span className="spinner" />正在读取旅行</div> : error ? <div className="directory-state error">{error}</div> : trips.length === 0 ? (
          <div className="empty-directory"><MapPin size={30} /><strong>还没有旅行</strong><p>选择一个目的地，创建你的第一份真实行程。</p><Link className="primary-link" to="/trips/new">创建旅行</Link></div>
        ) : (
          filteredTrips.length === 0 ? <div className="directory-state">当前筛选条件下没有旅行</div> : <div className="trip-grid">
            {filteredTrips.map((trip) => (
              <article className="trip-card" key={trip.id}>
                <Link className="trip-card-link" to={`/trips/${trip.id}/planner`}>
                  <div className="trip-card-map"><MapPin size={22} /><span>{trip.destination || "待选择城市"}</span><i className={`trip-status status-${trip.status ?? "upcoming"}`}>{statusLabel(trip.status ?? "upcoming")}</i></div>
                  <div className="trip-card-copy"><small>{formatDateRange(trip.startDate, trip.endDate)}</small><strong>{trip.title}</strong><p>{trip.accommodation ? `${trip.accommodationDistrict ?? ""} · ${trip.accommodation}` : "住宿地点待补充"}</p><footer><span>{formatFen(trip.totalBudgetFen)} 预算</span><i>{trip.updatedAt ? `${formatRelativeDate(trip.updatedAt)}更新` : "打开规划台 →"}</i></footer></div>
                </Link>
                <div className="trip-actions"><Link to={`/trips/${trip.id}/edit`} aria-label={`编辑${trip.title}`}><Pencil size={14} /></Link><button type="button" disabled={busyId === trip.id} onClick={() => void runAction(trip.id, "duplicate")} aria-label={`复制${trip.title}`}><Copy size={14} /></button>{trip.status !== "archived" && <button type="button" disabled={busyId === trip.id} onClick={() => void runAction(trip.id, "archive")} aria-label={`归档${trip.title}`}><Archive size={14} /></button>}<button className="danger" type="button" disabled={busyId === trip.id} onClick={() => void prepareDelete(trip)} aria-label={`删除${trip.title}`}><Trash2 size={14} /></button></div>
              </article>
            ))}
          </div>
        )}
      </section>
      {deleteTarget && <div className="modal-backdrop"><section className="confirm-modal" role="dialog" aria-modal="true" aria-label="确认删除旅行"><Trash2 size={24} /><h2>删除“{deleteTarget.trip.title}”？</h2><p>此操作将永久删除 {deleteTarget.dayPlans} 个日计划、{deleteTarget.activities} 个活动、{deleteTarget.candidates} 个地点和 {deleteTarget.expenses} 条消费记录。</p><div><button type="button" onClick={() => setDeleteTarget(null)}>取消</button><button className="danger-confirm" type="button" onClick={() => void confirmDelete()}>确认永久删除</button></div></section></div>}
    </main>
  );
}

function CreateTripPage({ repository }: { repository: TripPlanningRepository }) {
  const navigate = useNavigate();
  const { tripId } = useParams();
  const editing = Boolean(tripId);
  const defaults = useMemo(defaultDates, []);
  const [title, setTitle] = useState("");
  const [cityQuery, setCityQuery] = useState("");
  const [city, setCity] = useState<CitySuggestion | null>(null);
  const [cities, setCities] = useState<CitySuggestion[]>([]);
  const [startDate, setStartDate] = useState(defaults.start);
  const [endDate, setEndDate] = useState(defaults.end);
  const [budgetYuan, setBudgetYuan] = useState("3000");
  const [accommodation, setAccommodation] = useState("");
  const [accommodationPoi, setAccommodationPoi] = useState<AccommodationPoi | null>(null);
  const [accommodationResults, setAccommodationResults] = useState<AccommodationPoi[]>([]);
  const [accommodationLoading, setAccommodationLoading] = useState(false);
  const [tripVersion, setTripVersion] = useState(1);
  const [preferenceVersion, setPreferenceVersion] = useState(1);
  const [pace, setPace] = useState<TripPace>("balanced");
  const [interestCategories, setInterestCategories] = useState<InterestCategory[]>([]);
  const [transportModes, setTransportModes] = useState<PreferenceTransportMode[]>(["walk", "transit"]);
  const [dailyStartTime, setDailyStartTime] = useState("09:00");
  const [dailyEndTime, setDailyEndTime] = useState("21:00");
  const [mealPreferences, setMealPreferences] = useState("");
  const [avoidCategories, setAvoidCategories] = useState("");
  const [maxWalkingMinutes, setMaxWalkingMinutes] = useState("60");
  const [freeTextRequirements, setFreeTextRequirements] = useState("");
  const [confirmDayRemoval, setConfirmDayRemoval] = useState(false);
  const [cityLoading, setCityLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!tripId) return;
    Promise.all([repository.getTrip(tripId), repository.getTripPreferences(tripId)]).then(([trip, preferences]) => {
      setTitle(trip.title); setCityQuery(trip.destination); setCity({ name: trip.destination, adcode: trip.destinationAdcode ?? "", citycode: trip.destinationCitycode ?? "", coordinates: trip.center ?? [116.397428, 39.90923] });
      setStartDate(trip.startDate); setEndDate(trip.endDate); setBudgetYuan(String(trip.totalBudgetFen / 100)); setAccommodation(trip.accommodation); setTripVersion(trip.version ?? 1);
      if (trip.accommodationPoiId && trip.accommodationCoordinates) setAccommodationPoi({ poiId: trip.accommodationPoiId, name: trip.accommodation, address: trip.accommodationAddress ?? "", district: trip.accommodationDistrict ?? "", coordinates: trip.accommodationCoordinates, typeName: "住宿服务" });
      setPreferenceVersion(preferences.version); setPace(preferences.pace); setInterestCategories(preferences.interestCategories); setTransportModes(preferences.transportModes);
      setDailyStartTime(preferences.dailyStartTime); setDailyEndTime(preferences.dailyEndTime); setMealPreferences(preferences.mealPreferences);
      setAvoidCategories(preferences.avoidCategories.join("、")); setMaxWalkingMinutes(String(preferences.maxWalkingMinutes)); setFreeTextRequirements(preferences.freeTextRequirements);
    }).catch((cause) => setError(toOperationMessage(cause)));
  }, [repository, tripId]);

  useEffect(() => {
    if (city || cityQuery.trim().length < 2) {
      setCities([]);
      return;
    }
    const timer = window.setTimeout(() => {
      setCityLoading(true);
      repository.searchCities(cityQuery.trim())
        .then(setCities)
        .catch((cause) => setError(toOperationMessage(cause)))
        .finally(() => setCityLoading(false));
    }, 450);
    return () => window.clearTimeout(timer);
  }, [city, cityQuery, repository]);

  const searchAccommodation = async () => {
    if (!city || accommodation.trim().length < 1) return;
    setAccommodationLoading(true); setError(null);
    try { setAccommodationResults(await repository.searchAccommodationPois(accommodation.trim(), city.adcode || city.name)); }
    catch (cause) { setError(toOperationMessage(cause)); }
    finally { setAccommodationLoading(false); }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!city) {
      setError("请从高德城市查询结果中选择目的地");
      return;
    }
    const totalBudgetFen = Math.round(Number(budgetYuan) * 100);
    const dayCount = Math.max(1, Math.floor((new Date(`${endDate}T00:00:00`).getTime() - new Date(`${startDate}T00:00:00`).getTime()) / 86_400_000) + 1);
    setSubmitting(true);
    setError(null);
    try {
      const input = {
        title: title.trim() || `${city.name}之旅`,
        destination: city.name,
        destinationAdcode: city.adcode,
        destinationCitycode: city.citycode,
        center: city.coordinates,
        accommodation: accommodationPoi?.name ?? accommodation.trim(),
        accommodationPoiId: accommodationPoi?.poiId,
        accommodationAddress: accommodationPoi?.address,
        accommodationDistrict: accommodationPoi?.district,
        accommodationCoordinates: accommodationPoi?.coordinates,
        startDate,
        endDate,
        totalBudgetFen,
        dailyBudgetFen: Math.max(1, Math.floor(totalBudgetFen / dayCount)),
      };
      const trip = editing && tripId
        ? await repository.updateTrip(tripId, { ...input, version: tripVersion, confirmDayRemoval })
        : await repository.createTrip(input);
      await repository.updateTripPreferences(trip.id, {
        version: preferenceVersion,
        pace,
        interestCategories,
        transportModes,
        dailyStartTime,
        dailyEndTime,
        mealPreferences,
        avoidCategories: avoidCategories.split(/[、,，]/).map((item) => item.trim()).filter(Boolean),
        maxWalkingMinutes: Number(maxWalkingMinutes),
        freeTextRequirements,
      });
      navigate(`/trips/${trip.id}/planner`);
    } catch (cause) {
      const message = toOperationMessage(cause);
      if (message.includes("remove days containing activities")) {
        setConfirmDayRemoval(true);
        setError("缩短日期会删除包含活动的日计划。请再次提交以确认删除这些日期及其活动。");
      } else setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="create-page">
      <Link className="back-link" to="/trips"><ArrowLeft size={16} />返回旅行列表</Link>
      <form className="create-card" onSubmit={(event) => void submit(event)}>
        <span className="brand-mark large"><Compass size={26} /></span>
        <span className="eyebrow">{editing ? "EDIT JOURNEY" : "NEW JOURNEY"}</span><h1>{editing ? "编辑旅行" : "创建真实旅行"}</h1><p>城市与住宿均使用高德标准地点，地图、地点搜索与路线计算将绑定到这些位置锚点。</p>
        {error && <div className="form-error" role="alert">{error}</div>}
        <label><span>旅行名称</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：南昌周末之旅" maxLength={120} /></label>
        <label className="city-field"><span>目的地城市</span><div className="input-with-icon"><MapPin size={16} /><input value={cityQuery} onChange={(event) => { setCity(null); setCityQuery(event.target.value); }} placeholder="输入南昌、杭州、北京…" required /></div>
          {(cityLoading || cities.length > 0) && <div className="city-suggestions">{cityLoading ? <div><span className="spinner" />正在查询高德城市</div> : cities.map((item) => <button type="button" key={item.adcode} onClick={() => { setCity(item); setCityQuery(item.name); setCities([]); }}><strong>{item.name}</strong><small>行政区代码 {item.adcode}</small></button>)}</div>}
          {city && <small className="verified-city"><Sparkles size={12} />已选择高德标准城市 · {city.adcode}</small>}
        </label>
        <div className="form-row"><label><span>出发日期</span><input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required /></label><label><span>返程日期</span><input type="date" min={startDate} value={endDate} onChange={(event) => setEndDate(event.target.value)} required /></label></div>
        <label className="accommodation-field"><span>住宿地点（可选）</span><div className="poi-search-row"><input value={accommodation} onChange={(event) => { setAccommodation(event.target.value); setAccommodationPoi(null); setAccommodationResults([]); }} placeholder={city ? `搜索${city.name}酒店或民宿` : "请先选择城市"} disabled={!city} /><button type="button" disabled={!city || accommodationLoading || !accommodation.trim()} onClick={() => void searchAccommodation()}>{accommodationLoading ? "搜索中" : "搜索住宿"}</button></div>
          {accommodationResults.length > 0 && <div className="accommodation-results">{accommodationResults.map((item) => <button type="button" key={item.poiId} onClick={() => { setAccommodationPoi(item); setAccommodation(item.name); setAccommodationResults([]); }}><strong>{item.name}</strong><small>{item.district} · {item.address || item.typeName}{item.rating ? ` · ${item.rating}分` : ""}</small></button>)}</div>}
          {accommodationPoi && <small className="verified-city"><Sparkles size={12} />已选择高德住宿 POI · {accommodationPoi.district} · {accommodationPoi.address}</small>}
        </label>
        <div className="form-row"><label><span>总预算（元）</span><input type="number" min="1" step="1" value={budgetYuan} onChange={(event) => setBudgetYuan(event.target.value)} required /></label><div className="form-summary"><small>住宿锚点</small><strong>{accommodationPoi?.name ?? "尚未选择"}</strong><span>{accommodationPoi ? "将保存 POI ID、地址与坐标" : "可以稍后在编辑旅行中补充"}</span></div></div>
        <section className="preference-section" aria-labelledby="preference-title">
          <div><span className="eyebrow">PLANNING PROFILE</span><h2 id="preference-title">智能规划偏好</h2><p>这些约束将作为后续 Planner 与 Replanner 的统一输入。</p></div>
          <div className="form-row"><label><span>行程节奏</span><select value={pace} onChange={(event) => setPace(event.target.value as TripPace)}><option value="relaxed">轻松</option><option value="balanced">均衡</option><option value="intensive">紧凑</option></select></label><label><span>最长连续步行（分钟）</span><input type="number" min="1" max="480" value={maxWalkingMinutes} onChange={(event) => setMaxWalkingMinutes(event.target.value)} required /></label></div>
          <fieldset><legend>兴趣方向</legend><div className="preference-options">{INTEREST_OPTIONS.map((item) => <label key={item.value}><input type="checkbox" checked={interestCategories.includes(item.value)} onChange={() => setInterestCategories((current) => current.includes(item.value) ? current.filter((value) => value !== item.value) : [...current, item.value])} />{item.label}</label>)}</div></fieldset>
          <fieldset><legend>可接受交通方式</legend><div className="preference-options">{TRANSPORT_OPTIONS.map((item) => <label key={item.value}><input type="checkbox" checked={transportModes.includes(item.value)} onChange={() => setTransportModes((current) => current.includes(item.value) ? current.filter((value) => value !== item.value) : [...current, item.value])} />{item.label}</label>)}</div></fieldset>
          <div className="form-row"><label><span>每日最早出发</span><input type="time" value={dailyStartTime} onChange={(event) => setDailyStartTime(event.target.value)} required /></label><label><span>每日最晚结束</span><input type="time" value={dailyEndTime} onChange={(event) => setDailyEndTime(event.target.value)} required /></label></div>
          <label><span>饮食偏好</span><input value={mealPreferences} onChange={(event) => setMealPreferences(event.target.value)} maxLength={500} placeholder="例如：偏好本地小吃，不吃辣" /></label>
          <label><span>希望避开的内容</span><input value={avoidCategories} onChange={(event) => setAvoidCategories(event.target.value)} placeholder="用逗号分隔，例如：大型乐园、拥挤商场" /></label>
          <label><span>补充要求</span><textarea value={freeTextRequirements} onChange={(event) => setFreeTextRequirements(event.target.value)} maxLength={2000} placeholder="例如：每天下午保留一小时机动时间，晚上尽量回到住宿附近。" /></label>
        </section>
        <button className="submit-trip" disabled={submitting || !city} type="submit">{submitting ? "正在保存…" : confirmDayRemoval ? "确认删除缩短日期并保存" : editing ? "保存旅行设置" : "创建并开始规划"}</button>
      </form>
    </main>
  );
}

export function PlannerPage({ repository }: { repository: TripPlanningRepository }) {
  const { tripId = "" } = useParams();
  const [trip, setTrip] = useState<Trip | null>(null);
  const [days, setDays] = useState<DayPlan[]>([]);
  const [candidates, setCandidates] = useState<PlaceOption[]>([]);
  const [planningBudget, setPlanningBudget] = useState<PlanningBudget | null>(null);
  const [selectedDayId, setSelectedDayId] = useState<string | null>(null);
  const [selectedActivityId, setSelectedActivityId] = useState<string | null>(null);
  const [placesOpen, setPlacesOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [briefingOpen, setBriefingOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [isMutating, setIsMutating] = useState(false);
  const [routeMode, setRouteMode] = useState<RouteLeg["mode"]>("walk");

  const load = useCallback(async () => {
    try {
      const [nextTrip, nextDays, nextCandidates, nextBudget] = await Promise.all([
        repository.getTrip(tripId), repository.getDays(tripId), repository.getCandidates(tripId), repository.getPlanningBudget(tripId),
      ]);
      setTrip(nextTrip); setDays(nextDays); setCandidates(nextCandidates); setPlanningBudget(nextBudget);
      setSelectedDayId((current) => current && nextDays.some((day) => day.id === current) ? current : nextDays[0]?.id ?? null);
      setError(null);
    } catch (cause) { setError(toOperationMessage(cause)); } finally { setLoading(false); }
  }, [repository, tripId]);

  useEffect(() => { void load(); }, [load]);
  const selectedDay = days.find((day) => day.id === selectedDayId) ?? days[0];
  const selectedActivity = selectedDay?.activities.find((activity) => activity.id === selectedActivityId) ?? null;
  const budget = selectedDay ? planningBudget?.days.find((day) => day.dayPlanId === selectedDay.id) ?? null : null;
  const routeLegs = selectedDay?.routeLegs ?? [];
  const totalPlannedFen = planningBudget?.totalPlannedFen ?? 0;
  useEffect(() => { if (selectedDay?.routeMode) setRouteMode(selectedDay.routeMode); }, [selectedDay?.id, selectedDay?.routeMode]);

  const selectDay = (dayId: string) => { setSelectedDayId(dayId); setSelectedActivityId(days.find((item) => item.id === dayId)?.activities[0]?.id ?? null); };
  const selectActivity = useCallback((activityId: string) => setSelectedActivityId(activityId), []);
  const reorder = async (activityIds: string[]) => {
    if (!selectedDay || isMutating) return;
    const previousDays = days; const byId = new Map(selectedDay.activities.map((activity) => [activity.id, activity]));
    setDays((current) => current.map((day) => day.id === selectedDay.id ? { ...day, activities: activityIds.map((id) => byId.get(id)!).filter(Boolean) } : day));
    setIsMutating(true); setOperationError(null);
    try { const updated = await repository.reorderActivities(selectedDay.id, activityIds); setDays((current) => current.map((day) => day.id === updated.id ? updated : day)); await load(); }
    catch (cause) { setDays(previousDays); setOperationError(toOperationMessage(cause)); } finally { setIsMutating(false); }
  };
  const addActivity = async (place: PlaceOption) => {
    if (!selectedDay || isMutating) return; setIsMutating(true); setOperationError(null);
    try {
      const selection = "kind" in place ? place as PlaceSearchResult : (place as PlaceCandidate).id;
      const created = await repository.addActivity(selectedDay.id, selection);
      setSelectedActivityId(created.id);
      await load();
    }
    catch (cause) { setOperationError(toOperationMessage(cause)); } finally { setIsMutating(false); }
  };
  const removeActivity = async (activityId: string) => {
    if (isMutating) return; setIsMutating(true); setOperationError(null);
    try { await repository.removeActivity(activityId); setSelectedActivityId(null); await load(); }
    catch (cause) { setOperationError(toOperationMessage(cause)); } finally { setIsMutating(false); }
  };
  const updateActivity = async (activityId: string, input: ActivityUpdateInput) => {
    if (isMutating) return; setIsMutating(true); setOperationError(null);
    try {
      const updated = await repository.updateActivity(activityId, input);
      setDays((current) => current.map((day) => ({ ...day, activities: day.activities.map((item) => item.id === updated.id ? updated : item) })));
      await load();
    } catch (cause) { setOperationError(toOperationMessage(cause)); } finally { setIsMutating(false); }
  };
  const moveActivity = async (activity: Activity, targetDayId: string, targetPosition: number) => {
    if (isMutating) return;
    const previousDays = days;
    setDays((current) => moveActivityOptimistically(current, activity.id, targetDayId, targetPosition));
    setSelectedDayId(targetDayId); setSelectedActivityId(activity.id); setIsMutating(true); setOperationError(null);
    try {
      const result = await repository.moveActivity(activity.id, { version: activity.version, targetDayPlanId: targetDayId, targetPosition });
      setDays((current) => current.map((day) => day.id === result.sourceDay.id ? result.sourceDay : day.id === result.targetDay.id ? result.targetDay : day));
      await load();
    } catch (cause) {
      setDays(previousDays);
      setSelectedDayId(previousDays.find((day) => day.activities.some((item) => item.id === activity.id))?.id ?? previousDays[0]?.id ?? null);
      setOperationError(toOperationMessage(cause));
    } finally { setIsMutating(false); }
  };
  const searchPlaces = async (query: string, category?: PlaceCategory) => {
    setOperationError(null);
    try { setCandidates(query.trim() ? await repository.searchPlaces(tripId, query.trim(), category) : await repository.getCandidates(tripId)); }
    catch (cause) { setOperationError(toOperationMessage(cause)); }
  };
  const changeRouteMode = async (mode: RouteLeg["mode"]) => {
    if (isMutating || !selectedDay) return; setRouteMode(mode); setIsMutating(true); setOperationError(null);
    try { const updated = await repository.recalculateRoute(selectedDay.id, mode); setDays((current) => current.map((day) => day.id === updated.id ? updated : day)); }
    catch (cause) { setOperationError(toOperationMessage(cause)); } finally { setIsMutating(false); }
  };

  if (loading) return <LoadingScreen />;
  if (error || !trip || !selectedDay || !budget) return <ErrorScreen message={error ?? "旅行数据不完整"} onRetry={load} />;
  return (
    <main className="app-shell">
      <header className="topbar">
        <Link className="brand-lockup" to="/trips"><span className="brand-mark"><Compass size={19} /></span><strong>RoamSync</strong><i>TRIPS</i></Link>
        <div className="trip-identity"><span>{trip.title}</span><small><CalendarDays size={13} />{formatDateRange(trip.startDate, trip.endDate)}</small></div><div className="topbar-spacer" />
        <label className="route-mode-control"><RouteIcon size={15} /><span>交通</span><select value={routeMode} disabled={isMutating} onChange={(event) => void changeRouteMode(event.target.value as RouteLeg["mode"])}><option value="walk">步行</option><option value="transit">公交</option><option value="driving">驾车</option></select></label>
        <div className="total-budget"><WalletCards size={17} /><span><small>预计支出</small><strong>{formatFen(totalPlannedFen)}</strong></span><i>/ {formatFen(trip.totalBudgetFen)}</i></div>
        <span className="demo-badge"><Sparkles size={13} />真实高德 · PostgreSQL</span>
        <button className="topbar-button" type="button" onClick={() => setAiOpen(true)} aria-label="打开 AI 规划助手"><Sparkles size={17} /></button>
        <button className="topbar-button" type="button" onClick={() => setBriefingOpen(true)} aria-label="旅行总览与预订预览"><BedDouble size={17} /></button>
        <Link className="topbar-button" to={`/trips/${trip.id}/edit`} aria-label="编辑旅行设置"><Settings2 size={17} /></Link>
      </header>
      <div className="workspace">
        {operationError && <div className="operation-toast" role="alert"><span>{operationError}</span><button type="button" onClick={() => setOperationError(null)}>关闭</button></div>}
        <PlannerSidebar days={days} selectedDay={selectedDay} selectedActivityId={selectedActivityId} budget={budget} routeLegs={routeLegs} conflicts={selectedDay.conflicts ?? []} onSelectDay={selectDay} onSelectActivity={selectActivity} onReorder={reorder} onMoveActivity={moveActivity} onOpenPlaces={() => setPlacesOpen(true)} />
        <MapCanvas activities={selectedDay.activities} center={trip.center} accommodation={trip.accommodationCoordinates ? { name: trip.accommodation, coordinates: trip.accommodationCoordinates } : undefined} routeLegs={routeLegs} selectedActivityId={selectedActivityId} onSelectActivity={selectActivity} />
        <Inspector activity={selectedActivity} days={days} currentDayId={selectedDay.id} busy={isMutating} onClose={() => setSelectedActivityId(null)} onRemove={removeActivity} onSave={updateActivity} onMove={moveActivity} />
      </div>
      <PlacesDrawer open={placesOpen} candidates={candidates} dayLabel={selectedDay.label} destination={trip.destination} onClose={() => setPlacesOpen(false)} onAdd={addActivity} onSearch={searchPlaces} />
      <AiPlannerPanel open={aiOpen} tripId={trip.id} days={days} candidates={candidates.filter((item): item is PlaceCandidate => !("kind" in item))} repository={repository} onClose={() => setAiOpen(false)} onAccepted={load} />
      <TripBriefingDrawer open={briefingOpen} trip={trip} onClose={() => setBriefingOpen(false)} />
    </main>
  );
}

function LoadingScreen() { return <main className="status-screen"><span className="brand-mark large"><Compass size={26} /></span><span className="spinner dark" /><strong>正在准备旅行工作台</strong></main>; }
function ErrorScreen({ message, onRetry }: { message: string; onRetry: () => Promise<void> }) { return <main className="status-screen"><strong>无法打开旅行</strong><p>{message}</p><button type="button" onClick={() => void onRetry()}>重试</button><Link to="/trips">返回旅行列表</Link></main>; }
function formatDateRange(start: string, end: string) { const formatter = new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" }); return `${formatter.format(new Date(`${start}T00:00:00`))} — ${formatter.format(new Date(`${end}T00:00:00`))}`; }
function toOperationMessage(cause: unknown) { return cause instanceof Error ? cause.message : "操作失败，请稍后重试"; }
function defaultDates() { const start = new Date(); start.setDate(start.getDate() + 1); const end = new Date(start); end.setDate(end.getDate() + 2); return { start: toDateInput(start), end: toDateInput(end) }; }
function toDateInput(value: Date) { const local = new Date(value.getTime() - value.getTimezoneOffset() * 60_000); return local.toISOString().slice(0, 10); }
function statusLabel(status: "all" | NonNullable<Trip["status"]>) { return { all: "全部", upcoming: "即将出发", active: "进行中", completed: "已结束", archived: "已归档" }[status]; }
function formatRelativeDate(value: string) { const days = Math.floor((Date.now() - new Date(value).getTime()) / 86_400_000); return days <= 0 ? "今天" : days === 1 ? "昨天" : `${days}天前`; }

function moveActivityOptimistically(days: DayPlan[], activityId: string, targetDayId: string, targetPosition: number) {
  const sourceDay = days.find((day) => day.activities.some((activity) => activity.id === activityId));
  const activity = sourceDay?.activities.find((item) => item.id === activityId);
  if (!sourceDay || !activity) return days;
  return days.map((day) => {
    const without = day.activities.filter((item) => item.id !== activityId);
    if (day.id !== targetDayId) return day.id === sourceDay.id ? { ...day, activities: without } : day;
    const position = Math.min(Math.max(0, targetPosition), without.length);
    const next = [...without]; next.splice(position, 0, activity);
    return { ...day, activities: next };
  });
}
