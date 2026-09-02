import type {
  Activity,
  ActivityUpdateInput,
  ActivityMoveInput,
  ActivityMoveResult,
  AccommodationPoi,
  CitySuggestion,
  DayPlan,
  PlaceCandidate,
  PlaceSearchResult,
  PlanningBudget,
  PlanningContext,
  PlanningRun,
  PlanRevision,
  SourceRecord,
  Trip,
  TripCreateInput,
  TripDeletionPreview,
  TripPlanningRepository,
  TripUpdateInput,
  TripPreferences,
  TripPreferencesUpdateInput,
} from "../domain/types";

const API_BASE = "/api/v1";

interface ApiSourceRecord {
  id: string;
  title: string;
  url: string;
  provider: string;
  queried_at: string;
  confidence: SourceRecord["confidence"];
}

interface ApiPlaceCandidate {
  id: string;
  name: string;
  category: PlaceCandidate["category"];
  neighborhood: string;
  description: string;
  longitude: number;
  latitude: number;
  suggested_duration_minutes: number;
  estimated_cost_fen: number;
  rating: number;
  tags: string[];
  source: ApiSourceRecord;
}

interface ApiPlaceSearchResult {
  provider: "amap";
  provider_place_id: string;
  name: string;
  category: PlaceSearchResult["category"];
  neighborhood: string;
  description: string;
  longitude: number;
  latitude: number;
  suggested_duration_minutes: number;
  estimated_cost_fen: number;
  rating: number;
  tags: string[];
  source_url: string;
}

interface ApiActivity {
  id: string;
  place_id: string;
  name: string;
  custom_name: string | null;
  display_name: string;
  category: Activity["category"];
  neighborhood: string;
  longitude: number;
  latitude: number;
  scheduled_time: string;
  duration_minutes: number;
  estimated_cost_fen: number;
  status: Activity["status"];
  position: number;
  schedule_locked: boolean;
  version: number;
  note: string | null;
  updated_at: string;
  source: ApiSourceRecord;
}

interface ApiDayPlan {
  id: string;
  trip_id: string;
  date: string;
  label: string;
  theme: string;
  position: number;
  route_mode: "walk" | "transit" | "driving";
  activities: ApiActivity[];
  route_legs: Array<{
    id: string;
    from_activity_id: string;
    to_activity_id: string;
    position: number;
    mode: "walk" | "transit" | "driving";
    distance_meters: number;
    duration_minutes: number;
    provider: string;
    is_estimated: boolean;
    path: Array<[number, number]>;
    alternatives: Array<{
      distance_meters: number;
      duration_minutes: number;
      path: Array<[number, number]>;
    }>;
  }>;
  conflicts: Array<{ activity_id: string; code: "late_finish"; message: string }>;
}

interface ApiTrip {
  id: string;
  title: string;
  destination: string;
  accommodation: string;
  start_date: string;
  end_date: string;
  total_budget_fen: number;
  daily_budget_fen: number;
  currency: "CNY";
  destination_adcode: string;
  destination_citycode: string;
  center_longitude: number | null;
  center_latitude: number | null;
  accommodation_poi_id: string;
  accommodation_address: string;
  accommodation_district: string;
  accommodation_longitude: number | null;
  accommodation_latitude: number | null;
  status: "upcoming" | "active" | "completed" | "archived";
  updated_at: string;
  archived_at: string | null;
  version: number;
}

interface ApiLocationPoi {
  poi_id: string;
  name: string;
  address: string;
  district: string;
  longitude: number;
  latitude: number;
  type_name: string;
  rating: number | null;
}

interface ApiCitySuggestion {
  name: string;
  adcode: string;
  citycode: string;
  longitude: number;
  latitude: number;
}

interface ApiPlanningBudget {
  trip_id: string;
  total_planned_fen: number;
  total_remaining_fen: number;
  days: Array<{
    day_plan_id: string;
    date: string;
    planned_fen: number;
    remaining_fen: number;
    ratio: number;
    status: "comfortable" | "watch" | "over";
  }>;
}

interface ApiTripPreferences {
  trip_id: string;
  pace: TripPreferences["pace"];
  interest_categories: TripPreferences["interestCategories"];
  transport_modes: TripPreferences["transportModes"];
  daily_start_time: string;
  daily_end_time: string;
  meal_preferences: string;
  avoid_categories: string[];
  max_walking_minutes: number;
  free_text_requirements: string;
  version: number;
  updated_at: string;
}

interface ApiActualBudget {
  trip_id: string;
  total_budget_fen: number;
  total_spent_fen: number;
  total_remaining_fen: number;
  daily_budget_fen: number;
  today_spent_fen: number;
  today_remaining_fen: number;
  local_date: string;
}

interface ApiPlanningRun {
  id: string;
  trip_id: string;
  run_type: "initial_plan" | "replan";
  status: PlanningRun["status"];
  user_request: string;
  model_provider: string | null;
  model_name: string | null;
  token_usage: number;
  error_code: string | null;
  error_message: string | null;
  pending_interrupt: PlanningRun["pendingInterrupt"] | null;
}

interface ApiPlanRevision {
  id: string;
  planning_run_id: string;
  reason: string;
  proposed_snapshot: {
    activities: Array<{
      candidate_id: string;
      day_date: string;
      place_candidate_id: string;
      planned_start_time: string;
      duration_minutes: number;
      estimated_cost_fen: number;
      transport_mode_to_here: "walk" | "transit" | "driving";
      reason: string;
      locked: boolean;
    }>;
  };
  difference_summary: Record<string, unknown>;
  validation_result: Record<string, unknown>;
  source_ids: string[];
  status: PlanRevision["status"];
}

export class ApiRequestError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export class ApiTripPlanningRepository implements TripPlanningRepository {
  async listTrips(): Promise<Trip[]> {
    return (await request<ApiTrip[]>(`${API_BASE}/trips`)).map(mapTrip);
  }

  async createTrip(input: TripCreateInput): Promise<Trip> {
    const dto = await request<ApiTrip>(`${API_BASE}/trips`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: input.title,
        destination: input.destination,
        destination_adcode: input.destinationAdcode,
        destination_citycode: input.destinationCitycode,
        center_longitude: input.center[0],
        center_latitude: input.center[1],
        accommodation: input.accommodation,
        accommodation_poi_id: input.accommodationPoiId ?? "",
        accommodation_address: input.accommodationAddress ?? "",
        accommodation_district: input.accommodationDistrict ?? "",
        accommodation_longitude: input.accommodationCoordinates?.[0] ?? null,
        accommodation_latitude: input.accommodationCoordinates?.[1] ?? null,
        start_date: input.startDate,
        end_date: input.endDate,
        total_budget_fen: input.totalBudgetFen,
        daily_budget_fen: input.dailyBudgetFen,
        currency: "CNY",
        timezone: "Asia/Shanghai",
      }),
    });
    return mapTrip(dto);
  }

  async searchCities(query: string): Promise<CitySuggestion[]> {
    const items = await request<ApiCitySuggestion[]>(`${API_BASE}/locations/cities?${new URLSearchParams({ keyword: query })}`);
    return items.map((item) => ({
      name: item.name,
      adcode: item.adcode,
      citycode: item.citycode,
      coordinates: [item.longitude, item.latitude],
    }));
  }

  async searchAccommodationPois(query: string, city: string): Promise<AccommodationPoi[]> {
    const params = new URLSearchParams({ keyword: query, city, accommodation_only: "true" });
    return (await request<ApiLocationPoi[]>(`${API_BASE}/locations/pois?${params}`)).map((item) => ({
      poiId: item.poi_id,
      name: item.name,
      address: item.address,
      district: item.district,
      coordinates: [item.longitude, item.latitude],
      typeName: item.type_name,
      rating: item.rating ?? undefined,
    }));
  }

  async updateTrip(tripId: string, input: TripUpdateInput): Promise<Trip> {
    const body: Record<string, unknown> = {
      version: input.version,
      confirm_day_removal: input.confirmDayRemoval ?? false,
    };
    if (input.title !== undefined) body.title = input.title;
    if (input.destination !== undefined) body.destination = input.destination;
    if (input.destinationAdcode !== undefined) body.destination_adcode = input.destinationAdcode;
    if (input.destinationCitycode !== undefined) body.destination_citycode = input.destinationCitycode;
    if (input.center !== undefined) { body.center_longitude = input.center[0]; body.center_latitude = input.center[1]; }
    if (input.accommodation !== undefined) body.accommodation = input.accommodation;
    if (input.accommodationPoiId !== undefined) body.accommodation_poi_id = input.accommodationPoiId;
    if (input.accommodationAddress !== undefined) body.accommodation_address = input.accommodationAddress;
    if (input.accommodationDistrict !== undefined) body.accommodation_district = input.accommodationDistrict;
    if (input.accommodationCoordinates !== undefined) { body.accommodation_longitude = input.accommodationCoordinates[0]; body.accommodation_latitude = input.accommodationCoordinates[1]; }
    if (input.startDate !== undefined) body.start_date = input.startDate;
    if (input.endDate !== undefined) body.end_date = input.endDate;
    if (input.totalBudgetFen !== undefined) body.total_budget_fen = input.totalBudgetFen;
    if (input.dailyBudgetFen !== undefined) body.daily_budget_fen = input.dailyBudgetFen;
    return mapTrip(await request<ApiTrip>(`${API_BASE}/trips/${tripId}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }));
  }

  async getTripPreferences(tripId: string): Promise<TripPreferences> {
    return mapPreferences(await request<ApiTripPreferences>(`${API_BASE}/trips/${tripId}/preferences`));
  }

  async updateTripPreferences(tripId: string, input: TripPreferencesUpdateInput): Promise<TripPreferences> {
    return mapPreferences(await request<ApiTripPreferences>(`${API_BASE}/trips/${tripId}/preferences`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        version: input.version,
        pace: input.pace,
        interest_categories: input.interestCategories,
        transport_modes: input.transportModes,
        daily_start_time: input.dailyStartTime,
        daily_end_time: input.dailyEndTime,
        meal_preferences: input.mealPreferences,
        avoid_categories: input.avoidCategories,
        max_walking_minutes: input.maxWalkingMinutes,
        free_text_requirements: input.freeTextRequirements,
      }),
    }));
  }

  async getPlanningContext(tripId: string): Promise<PlanningContext> {
    const dto = await request<{
      trip: ApiTrip;
      preferences: ApiTripPreferences;
      days: ApiDayPlan[];
      candidates: ApiPlaceCandidate[];
      actual_budget: ApiActualBudget;
      planning_budget: ApiPlanningBudget;
      generated_at: string;
    }>(`${API_BASE}/trips/${tripId}/planning-context`);
    return {
      trip: mapTrip(dto.trip),
      preferences: mapPreferences(dto.preferences),
      days: dto.days.map(mapDay),
      candidates: dto.candidates.map(mapCandidate),
      actualBudget: {
        tripId: dto.actual_budget.trip_id,
        totalBudgetFen: dto.actual_budget.total_budget_fen,
        totalSpentFen: dto.actual_budget.total_spent_fen,
        totalRemainingFen: dto.actual_budget.total_remaining_fen,
        dailyBudgetFen: dto.actual_budget.daily_budget_fen,
        todaySpentFen: dto.actual_budget.today_spent_fen,
        todayRemainingFen: dto.actual_budget.today_remaining_fen,
        localDate: dto.actual_budget.local_date,
      },
      planningBudget: mapPlanningBudget(dto.planning_budget),
      generatedAt: dto.generated_at,
    };
  }

  async duplicateTrip(tripId: string): Promise<Trip> {
    return mapTrip(await request<ApiTrip>(`${API_BASE}/trips/${tripId}/duplicate`, { method: "POST" }));
  }

  async archiveTrip(tripId: string): Promise<Trip> {
    return mapTrip(await request<ApiTrip>(`${API_BASE}/trips/${tripId}/archive`, { method: "POST" }));
  }

  async getTripDeletionPreview(tripId: string): Promise<TripDeletionPreview> {
    const item = await request<{ trip_id: string; day_plans: number; activities: number; candidates: number; expenses: number }>(`${API_BASE}/trips/${tripId}/deletion-preview`);
    return { tripId: item.trip_id, dayPlans: item.day_plans, activities: item.activities, candidates: item.candidates, expenses: item.expenses };
  }

  async deleteTrip(tripId: string): Promise<void> {
    await request<void>(`${API_BASE}/trips/${tripId}?confirm=true`, { method: "DELETE" });
  }

  async getTrip(tripId: string): Promise<Trip> {
    const dto = await request<ApiTrip>(`${API_BASE}/trips/${tripId}`);
    return mapTrip(dto);
  }

  async getDays(tripId: string): Promise<DayPlan[]> {
    const items = await request<ApiDayPlan[]>(`${API_BASE}/trips/${tripId}/days`);
    return items.map(mapDay);
  }

  async getCandidates(tripId: string): Promise<PlaceCandidate[]> {
    const items = await request<ApiPlaceCandidate[]>(`${API_BASE}/trips/${tripId}/candidates`);
    return items.map(mapCandidate);
  }

  async searchPlaces(tripId: string, query: string, category?: PlaceCandidate["category"]): Promise<PlaceSearchResult[]> {
    const params = new URLSearchParams({ q: query });
    if (category) params.set("category", category);
    const items = await request<ApiPlaceSearchResult[]>(`${API_BASE}/trips/${tripId}/places/search?${params}`);
    return items.map(mapSearchResult);
  }

  async getPlanningBudget(tripId: string): Promise<PlanningBudget> {
    return mapPlanningBudget(await request<ApiPlanningBudget>(`${API_BASE}/trips/${tripId}/planning-budget`));
  }

  async addActivity(dayId: string, place: string | PlaceSearchResult): Promise<Activity> {
    const dto = await request<ApiActivity>(`${API_BASE}/day-plans/${dayId}/activities`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(typeof place === "string" ? { place_id: place } : {
        place_snapshot: {
          provider: place.provider,
          provider_place_id: place.providerPoiId,
          name: place.name,
          category: place.category,
          neighborhood: place.neighborhood,
          description: place.description,
          longitude: place.coordinates[0],
          latitude: place.coordinates[1],
          suggested_duration_minutes: place.suggestedDurationMinutes,
          estimated_cost_fen: place.estimatedCostFen,
          rating: place.rating,
          tags: place.tags,
          source_url: place.sourceUrl,
        },
      }),
    });
    return mapActivity(dto);
  }

  async reorderActivities(dayId: string, activityIds: string[]): Promise<DayPlan> {
    const dto = await request<ApiDayPlan>(`${API_BASE}/day-plans/${dayId}/activity-order`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ activity_ids: activityIds }),
    });
    return mapDay(dto);
  }

  async updateActivity(activityId: string, input: ActivityUpdateInput): Promise<Activity> {
    const body: Record<string, unknown> = { version: input.version };
    if (input.customName !== undefined) body.custom_name = input.customName;
    if (input.scheduledTime !== undefined) body.scheduled_time = input.scheduledTime;
    if (input.durationMinutes !== undefined) body.duration_minutes = input.durationMinutes;
    if (input.estimatedCostFen !== undefined) body.estimated_cost_fen = input.estimatedCostFen;
    if (input.status !== undefined) body.status = input.status;
    if (input.note !== undefined) body.note = input.note;
    if (input.scheduleLocked !== undefined) body.schedule_locked = input.scheduleLocked;
    return mapActivity(await request<ApiActivity>(`${API_BASE}/activities/${activityId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }));
  }

  async moveActivity(activityId: string, input: ActivityMoveInput): Promise<ActivityMoveResult> {
    const dto = await request<{ activity_id: string; source_day: ApiDayPlan; target_day: ApiDayPlan }>(
      `${API_BASE}/activities/${activityId}/move`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          version: input.version,
          target_day_plan_id: input.targetDayPlanId,
          target_position: input.targetPosition,
        }),
      },
    );
    return { activityId: dto.activity_id, sourceDay: mapDay(dto.source_day), targetDay: mapDay(dto.target_day) };
  }

  async recalculateRoute(dayId: string, mode: "walk" | "transit" | "driving"): Promise<DayPlan> {
    const dto = await request<ApiDayPlan>(`${API_BASE}/day-plans/${dayId}/route`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    return mapDay(dto);
  }

  async removeActivity(activityId: string): Promise<void> {
    await request<void>(`${API_BASE}/activities/${activityId}`, { method: "DELETE" });
  }

  async createPlanningRun(tripId: string, userRequest: string): Promise<PlanningRun> {
    return mapPlanningRun(await request<ApiPlanningRun>(`${API_BASE}/trips/${tripId}/planning-runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_type: "replan", user_request: userRequest }),
    }));
  }

  async getPlanningRun(runId: string): Promise<PlanningRun> {
    return mapPlanningRun(await request<ApiPlanningRun>(`${API_BASE}/planning-runs/${runId}`));
  }

  async answerPlanningRun(runId: string, answer: string): Promise<PlanningRun> {
    const result = await request<{ run: ApiPlanningRun }>(`${API_BASE}/planning-runs/${runId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: "clarify", answer }),
    });
    return mapPlanningRun(result.run);
  }

  async getPlanRevision(runId: string): Promise<PlanRevision> {
    return mapPlanRevision(await request<ApiPlanRevision>(`${API_BASE}/planning-runs/${runId}/revision`));
  }

  async acceptPlanRevision(revisionId: string): Promise<PlanRevision> {
    return mapPlanRevision(await request<ApiPlanRevision>(`${API_BASE}/plan-revisions/${revisionId}/accept`, { method: "POST" }));
  }

  async rejectPlanRevision(revisionId: string): Promise<PlanRevision> {
    return mapPlanRevision(await request<ApiPlanRevision>(`${API_BASE}/plan-revisions/${revisionId}/reject`, { method: "POST" }));
  }

}

function mapPlanningRun(dto: ApiPlanningRun): PlanningRun {
  return {
    id: dto.id, tripId: dto.trip_id, runType: dto.run_type, status: dto.status,
    userRequest: dto.user_request, modelProvider: dto.model_provider ?? undefined,
    modelName: dto.model_name ?? undefined, tokenUsage: dto.token_usage,
    errorCode: dto.error_code ?? undefined, errorMessage: dto.error_message ?? undefined,
    pendingInterrupt: dto.pending_interrupt ?? undefined,
  };
}

function mapPlanRevision(dto: ApiPlanRevision): PlanRevision {
  return {
    id: dto.id,
    planningRunId: dto.planning_run_id,
    reason: dto.reason,
    activities: dto.proposed_snapshot.activities.map((item) => ({
      candidateId: item.candidate_id,
      dayDate: item.day_date,
      placeCandidateId: item.place_candidate_id,
      plannedStartTime: item.planned_start_time.slice(0, 5),
      durationMinutes: item.duration_minutes,
      estimatedCostFen: item.estimated_cost_fen,
      transportModeToHere: item.transport_mode_to_here,
      reason: item.reason,
      locked: item.locked,
    })),
    differenceSummary: dto.difference_summary,
    validationResult: dto.validation_result,
    sourceIds: dto.source_ids,
    status: dto.status,
  };
}

function mapPreferences(dto: ApiTripPreferences): TripPreferences {
  return {
    tripId: dto.trip_id,
    pace: dto.pace,
    interestCategories: dto.interest_categories,
    transportModes: dto.transport_modes,
    dailyStartTime: dto.daily_start_time.slice(0, 5),
    dailyEndTime: dto.daily_end_time.slice(0, 5),
    mealPreferences: dto.meal_preferences,
    avoidCategories: dto.avoid_categories,
    maxWalkingMinutes: dto.max_walking_minutes,
    freeTextRequirements: dto.free_text_requirements,
    version: dto.version,
    updatedAt: dto.updated_at,
  };
}

function mapPlanningBudget(dto: ApiPlanningBudget): PlanningBudget {
  return {
    tripId: dto.trip_id,
    totalPlannedFen: dto.total_planned_fen,
    totalRemainingFen: dto.total_remaining_fen,
    days: dto.days.map((day) => ({
      dayPlanId: day.day_plan_id,
      date: day.date,
      plannedFen: day.planned_fen,
      remainingFen: day.remaining_fen,
      ratio: day.ratio,
      status: day.status,
    })),
  };
}

function mapTrip(dto: ApiTrip): Trip {
  const center = dto.center_longitude !== null && dto.center_latitude !== null
    ? [dto.center_longitude, dto.center_latitude] as const
    : undefined;
  const accommodationCoordinates = dto.accommodation_longitude !== null && dto.accommodation_latitude !== null
    ? [dto.accommodation_longitude, dto.accommodation_latitude] as const
    : undefined;
  return {
    id: dto.id,
    title: dto.title,
    destination: dto.destination,
    accommodation: dto.accommodation,
    startDate: dto.start_date,
    endDate: dto.end_date,
    totalBudgetFen: dto.total_budget_fen,
    dailyBudgetFen: dto.daily_budget_fen,
    currency: dto.currency,
    destinationAdcode: dto.destination_adcode,
    destinationCitycode: dto.destination_citycode,
    center,
    accommodationPoiId: dto.accommodation_poi_id,
    accommodationAddress: dto.accommodation_address,
    accommodationDistrict: dto.accommodation_district,
    accommodationCoordinates,
    status: dto.status,
    updatedAt: dto.updated_at,
    archivedAt: dto.archived_at ?? undefined,
    version: dto.version,
  };
}

function mapSource(dto: ApiSourceRecord): SourceRecord {
  return { id: dto.id, title: dto.title, url: dto.url, provider: dto.provider, queriedAt: dto.queried_at, confidence: dto.confidence };
}

function mapCandidate(dto: ApiPlaceCandidate): PlaceCandidate {
  return {
    id: dto.id,
    name: dto.name,
    category: dto.category,
    neighborhood: dto.neighborhood,
    description: dto.description,
    coordinates: [dto.longitude, dto.latitude],
    suggestedDurationMinutes: dto.suggested_duration_minutes,
    estimatedCostFen: dto.estimated_cost_fen,
    rating: dto.rating,
    tags: dto.tags,
    source: mapSource(dto.source),
  };
}

function mapSearchResult(dto: ApiPlaceSearchResult): PlaceSearchResult {
  return {
    kind: "search",
    provider: dto.provider,
    providerPoiId: dto.provider_place_id,
    name: dto.name,
    category: dto.category,
    neighborhood: dto.neighborhood,
    description: dto.description,
    coordinates: [dto.longitude, dto.latitude],
    suggestedDurationMinutes: dto.suggested_duration_minutes,
    estimatedCostFen: dto.estimated_cost_fen,
    rating: dto.rating,
    tags: dto.tags,
    sourceUrl: dto.source_url,
  };
}

function mapActivity(dto: ApiActivity): Activity {
  return {
    id: dto.id,
    placeId: dto.place_id,
    name: dto.display_name,
    originalName: dto.name,
    customName: dto.custom_name ?? undefined,
    category: dto.category,
    neighborhood: dto.neighborhood,
    coordinates: [dto.longitude, dto.latitude],
    scheduledTime: dto.scheduled_time.slice(0, 5),
    durationMinutes: dto.duration_minutes,
    estimatedCostFen: dto.estimated_cost_fen,
    status: dto.status,
    scheduleLocked: dto.schedule_locked,
    version: dto.version,
    updatedAt: dto.updated_at,
    note: dto.note ?? undefined,
    source: mapSource(dto.source),
  };
}

function mapDay(dto: ApiDayPlan): DayPlan {
  return {
    id: dto.id,
    tripId: dto.trip_id,
    date: dto.date,
    label: dto.label,
    theme: dto.theme,
    activities: dto.activities.map(mapActivity),
    routeMode: dto.route_mode ?? "walk",
    routeLegs: (dto.route_legs ?? []).map((leg) => ({
      id: leg.id,
      fromActivityId: leg.from_activity_id,
      toActivityId: leg.to_activity_id,
      distanceMeters: leg.distance_meters,
      durationMinutes: leg.duration_minutes,
      mode: leg.mode,
      provider: leg.provider,
      isEstimated: leg.is_estimated,
      path: leg.path ?? [],
      alternatives: (leg.alternatives ?? []).map((alternative) => ({
        distanceMeters: alternative.distance_meters,
        durationMinutes: alternative.duration_minutes,
        path: alternative.path,
      })),
    })),
    conflicts: (dto.conflicts ?? []).map((conflict) => ({
      activityId: conflict.activity_id,
      code: conflict.code,
      message: conflict.message,
    })),
  };
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let detail = `请求失败（HTTP ${response.status}）`;
    try {
      const body = await response.json() as { detail?: string | { message?: string } };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail?.message) detail = body.detail.message;
    } catch {
      // Keep the deterministic fallback message.
    }
    throw new ApiRequestError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}
