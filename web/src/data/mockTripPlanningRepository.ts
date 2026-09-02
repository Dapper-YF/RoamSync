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
  Trip,
  TripCreateInput,
  TripDeletionPreview,
  TripPlanningRepository,
  TripUpdateInput,
  TripPreferences,
  TripPreferencesUpdateInput,
} from "../domain/types";
import {
  DEMO_SCHEMA_VERSION,
  DEMO_STORAGE_KEY,
  DEMO_TRIP_ID,
  DEMO_TRIP_UUID,
  demoCandidates,
  demoDays,
  demoTrip,
} from "./demoData";
import { buildRouteLegs } from "../utils/planner";

interface PersistedDemoState {
  version: number;
  days: DayPlan[];
}

const clone = <T,>(value: T): T => structuredClone(value);

export class LocalTripPlanningRepository implements TripPlanningRepository {
  private days: DayPlan[];
  private preferences: TripPreferences = {
    tripId: DEMO_TRIP_UUID,
    pace: "balanced",
    interestCategories: ["culture", "food"],
    transportModes: ["walk", "transit"],
    dailyStartTime: "09:00",
    dailyEndTime: "21:00",
    mealPreferences: "",
    avoidCategories: [],
    maxWalkingMinutes: 60,
    freeTextRequirements: "",
    version: 1,
    updatedAt: new Date(0).toISOString(),
  };

  constructor(private readonly storage: Storage = window.localStorage) {
    this.days = this.loadDays();
  }

  async listTrips(): Promise<Trip[]> {
    return [clone(demoTrip)];
  }

  async createTrip(input: TripCreateInput): Promise<Trip> {
    return {
      ...clone(demoTrip),
      title: input.title,
      destination: input.destination,
      startDate: input.startDate,
      endDate: input.endDate,
      totalBudgetFen: input.totalBudgetFen,
      dailyBudgetFen: input.dailyBudgetFen,
      center: input.center,
    };
  }

  async searchCities(query: string): Promise<CitySuggestion[]> {
    return query.includes("南昌")
      ? [{ name: "南昌市", adcode: "360100", citycode: "0791", coordinates: [115.857972, 28.682976] }]
      : [];
  }

  async searchAccommodationPois(query: string, city: string): Promise<AccommodationPoi[]> {
    return query.trim()
      ? [{ poiId: "mock-hotel", name: `${city}中心酒店`, address: "测试路 1 号", district: city, coordinates: [115.858, 28.683], typeName: "住宿服务", rating: 4.6 }]
      : [];
  }

  async updateTrip(tripId: string, input: TripUpdateInput): Promise<Trip> {
    this.assertDemoTrip(tripId);
    return { ...clone(demoTrip), title: input.title ?? demoTrip.title, version: input.version + 1 };
  }

  async getTripPreferences(tripId: string): Promise<TripPreferences> {
    this.assertDemoTrip(tripId);
    return clone(this.preferences);
  }

  async updateTripPreferences(tripId: string, input: TripPreferencesUpdateInput): Promise<TripPreferences> {
    this.assertDemoTrip(tripId);
    this.preferences = {
      ...clone(input),
      tripId: DEMO_TRIP_UUID,
      version: input.version + 1,
      updatedAt: new Date().toISOString(),
    };
    return clone(this.preferences);
  }

  async getPlanningContext(tripId: string): Promise<PlanningContext> {
    this.assertDemoTrip(tripId);
    const planningBudget = await this.getPlanningBudget(tripId);
    return {
      trip: clone(demoTrip),
      preferences: clone(this.preferences),
      days: clone(this.days),
      candidates: await this.getCandidates(tripId),
      actualBudget: {
        tripId,
        totalBudgetFen: demoTrip.totalBudgetFen,
        totalSpentFen: 0,
        totalRemainingFen: demoTrip.totalBudgetFen,
        dailyBudgetFen: demoTrip.dailyBudgetFen,
        todaySpentFen: 0,
        todayRemainingFen: demoTrip.dailyBudgetFen,
        localDate: demoTrip.startDate,
      },
      planningBudget,
      generatedAt: new Date().toISOString(),
    };
  }

  async duplicateTrip(tripId: string): Promise<Trip> {
    this.assertDemoTrip(tripId);
    return { ...clone(demoTrip), id: "demo-copy", title: `${demoTrip.title}（副本）` };
  }

  async archiveTrip(tripId: string): Promise<Trip> {
    this.assertDemoTrip(tripId);
    return { ...clone(demoTrip), status: "archived" };
  }

  async getTripDeletionPreview(tripId: string): Promise<TripDeletionPreview> {
    return { tripId, dayPlans: this.days.length, activities: this.days.flatMap((day) => day.activities).length, candidates: demoCandidates.length, expenses: 0 };
  }

  async deleteTrip(tripId: string): Promise<void> { this.assertDemoTrip(tripId); }

  async getTrip(tripId: string): Promise<Trip> {
    this.assertDemoTrip(tripId);
    return clone(demoTrip);
  }

  async getDays(tripId: string): Promise<DayPlan[]> {
    this.assertDemoTrip(tripId);
    return clone(this.days);
  }

  async getCandidates(tripId: string): Promise<PlaceCandidate[]> {
    this.assertDemoTrip(tripId);
    const usedPlaceIds = new Set(this.days.flatMap((day) => day.activities.map((item) => item.placeId)));
    return clone(demoCandidates.filter((candidate) => !usedPlaceIds.has(candidate.id)));
  }

  async searchPlaces(tripId: string, query: string, category?: PlaceCandidate["category"]): Promise<PlaceSearchResult[]> {
    const candidates = await this.getCandidates(tripId);
    const normalized = query.trim().toLocaleLowerCase("zh-CN");
    return candidates.filter((place) =>
      (!category || place.category === category)
      && (place.name.toLocaleLowerCase("zh-CN").includes(normalized) || place.description.toLocaleLowerCase("zh-CN").includes(normalized))
    ).map((place) => ({
      kind: "search" as const,
      provider: "amap" as const,
      providerPoiId: `mock-${place.id}`,
      name: place.name,
      category: place.category,
      neighborhood: place.neighborhood,
      description: place.description,
      coordinates: place.coordinates,
      suggestedDurationMinutes: place.suggestedDurationMinutes,
      estimatedCostFen: place.estimatedCostFen,
      rating: place.rating,
      tags: place.tags,
      sourceUrl: place.source.url,
    }));
  }

  async getPlanningBudget(tripId: string): Promise<PlanningBudget> {
    this.assertDemoTrip(tripId);
    const days = this.days.map((day) => {
      const plannedFen = day.activities.reduce((total, activity) => total + activity.estimatedCostFen, 0);
      const ratio = plannedFen / demoTrip.dailyBudgetFen;
      return {
        dayPlanId: day.id,
        date: day.date,
        plannedFen,
        remainingFen: demoTrip.dailyBudgetFen - plannedFen,
        ratio,
        status: ratio > 1 ? "over" as const : ratio >= 0.8 ? "watch" as const : "comfortable" as const,
      };
    });
    const totalPlannedFen = days.reduce((total, day) => total + day.plannedFen, 0);
    return {
      tripId,
      totalPlannedFen,
      totalRemainingFen: demoTrip.totalBudgetFen - totalPlannedFen,
      days,
    };
  }

  async addActivity(dayId: string, selection: string | PlaceSearchResult): Promise<Activity> {
    const day = this.requireDay(dayId);
    const placeId = typeof selection === "string" ? selection : selection.providerPoiId.replace(/^mock-/, "");
    const place = demoCandidates.find((candidate) => candidate.id === placeId);
    if (!place) throw new Error("候选地点不存在");
    if (this.days.some((item) => item.activities.some((activity) => activity.placeId === placeId))) {
      throw new Error("该地点已经加入行程");
    }
    const activity: Activity = {
      id: `activity-${place.id}`,
      placeId: place.id,
      name: place.name,
      originalName: place.name,
      category: place.category,
      neighborhood: place.neighborhood,
      coordinates: place.coordinates,
      scheduledTime: this.nextTime(day.activities),
      durationMinutes: place.suggestedDurationMinutes,
      estimatedCostFen: place.estimatedCostFen,
      status: "planned",
      scheduleLocked: false,
      version: 1,
      updatedAt: new Date().toISOString(),
      source: place.source,
    };
    day.activities.push(activity);
    this.updateMockRoute(day);
    this.persist();
    return clone(activity);
  }

  async updateActivity(activityId: string, input: ActivityUpdateInput): Promise<Activity> {
    const activity = this.days.flatMap((day) => day.activities).find((item) => item.id === activityId);
    if (!activity) throw new Error("活动不存在");
    if (activity.version !== input.version) throw new Error("活动已被其他操作修改，请重新加载后再保存");
    if (input.customName !== undefined) activity.customName = input.customName?.trim() || undefined;
    if (input.customName !== undefined) activity.name = activity.customName || activity.originalName;
    if (input.scheduledTime !== undefined) activity.scheduledTime = input.scheduledTime;
    if (input.durationMinutes !== undefined) activity.durationMinutes = input.durationMinutes;
    if (input.estimatedCostFen !== undefined) activity.estimatedCostFen = input.estimatedCostFen;
    if (input.status !== undefined) activity.status = input.status;
    if (input.note !== undefined) activity.note = input.note?.trim() || undefined;
    if (input.scheduleLocked !== undefined) activity.scheduleLocked = input.scheduleLocked;
    activity.version += 1;
    activity.updatedAt = new Date().toISOString();
    this.persist();
    return clone(activity);
  }

  async moveActivity(activityId: string, input: ActivityMoveInput): Promise<ActivityMoveResult> {
    const sourceDay = this.days.find((day) => day.activities.some((item) => item.id === activityId));
    const targetDay = this.days.find((day) => day.id === input.targetDayPlanId);
    if (!sourceDay || !targetDay) throw new Error("目标日期不存在");
    const sourceIndex = sourceDay.activities.findIndex((item) => item.id === activityId);
    const activity = sourceDay.activities[sourceIndex];
    if (activity.version !== input.version) throw new Error("活动已被其他操作修改，请重新加载后再移动");
    const targetWithoutActivity = targetDay.activities.filter((item) => item.id !== activityId);
    if (input.targetPosition < 0 || input.targetPosition > targetWithoutActivity.length) throw new Error("目标位置无效");
    if (sourceDay.id !== targetDay.id && targetWithoutActivity.some((item) => item.placeId === activity.placeId)) throw new Error("目标日期已经包含该地点");
    sourceDay.activities.splice(sourceIndex, 1);
    targetWithoutActivity.splice(input.targetPosition, 0, activity);
    targetDay.activities = targetWithoutActivity;
    activity.version += 1;
    activity.updatedAt = new Date().toISOString();
    this.updateMockRoute(sourceDay);
    if (targetDay.id !== sourceDay.id) this.updateMockRoute(targetDay);
    this.persist();
    return { activityId, sourceDay: clone(sourceDay), targetDay: clone(targetDay) };
  }

  async reorderActivities(dayId: string, activityIds: string[]): Promise<DayPlan> {
    const day = this.requireDay(dayId);
    if (activityIds.length !== day.activities.length) throw new Error("排序数据不完整");
    const byId = new Map(day.activities.map((activity) => [activity.id, activity]));
    const ordered = activityIds.map((id) => byId.get(id));
    if (ordered.some((activity) => !activity)) throw new Error("排序包含未知活动");
    day.activities = ordered as Activity[];
    this.updateMockRoute(day);
    this.persist();
    return clone(day);
  }

  async recalculateRoute(dayId: string, mode: "walk" | "transit" | "driving"): Promise<DayPlan> {
    const day = this.requireDay(dayId);
    this.updateMockRoute(day, mode);
    this.persist();
    return clone(day);
  }

  async removeActivity(activityId: string): Promise<void> {
    const day = this.days.find((item) => item.activities.some((activity) => activity.id === activityId));
    if (!day) throw new Error("活动不存在");
    day.activities = day.activities.filter((activity) => activity.id !== activityId);
    this.updateMockRoute(day);
    this.persist();
  }

  async resetDemo(): Promise<void> {
    this.days = clone(demoDays);
    this.persist();
  }

  private assertDemoTrip(tripId: string) {
    if (tripId !== DEMO_TRIP_ID && tripId !== DEMO_TRIP_UUID) throw new Error("演示旅行不存在");
  }

  private requireDay(dayId: string) {
    const day = this.days.find((item) => item.id === dayId);
    if (!day) throw new Error("行程日期不存在");
    return day;
  }

  private nextTime(activities: Activity[]) {
    if (activities.length === 0) return "09:00";
    const last = activities.at(-1)!;
    const [hours, minutes] = last.scheduledTime.split(":").map(Number);
    const end = hours * 60 + minutes + last.durationMinutes + 30;
    return `${String(Math.min(Math.floor(end / 60), 22)).padStart(2, "0")}:${String(end % 60).padStart(2, "0")}`;
  }

  private updateMockRoute(day: DayPlan, forcedMode?: "walk" | "transit" | "driving") {
    day.routeMode = forcedMode ?? day.routeMode ?? "walk";
    day.routeLegs = buildRouteLegs(day.activities).map((leg) => ({ ...leg, mode: day.routeMode! }));
  }

  private loadDays(): DayPlan[] {
    try {
      const raw = this.storage.getItem(DEMO_STORAGE_KEY);
      if (!raw) return clone(demoDays);
      const saved = JSON.parse(raw) as PersistedDemoState;
      if (saved.version !== DEMO_SCHEMA_VERSION || !Array.isArray(saved.days)) return clone(demoDays);
      return saved.days;
    } catch {
      return clone(demoDays);
    }
  }

  private persist() {
    const state: PersistedDemoState = { version: DEMO_SCHEMA_VERSION, days: this.days };
    this.storage.setItem(DEMO_STORAGE_KEY, JSON.stringify(state));
  }
}
