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
  Trip,
  TripExecution,
  TripExecutionAction,
  TripCreateInput,
  TripDeletionPreview,
  TripPlanningRepository,
  DynamicReplanTrigger,
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

const DEMO_EXECUTION_STORAGE_KEY = "roamsync-demo-execution-v1";

const clone = <T,>(value: T): T => structuredClone(value);

export class LocalTripPlanningRepository implements TripPlanningRepository {
  private days: DayPlan[];
  private planningRuns: PlanningRun[] = [];
  private execution: TripExecution | null;
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
    this.execution = this.loadExecution();
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
    externalFacts: {},
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
      const ratio = demoTrip.dailyBudgetFen == null ? null : plannedFen / demoTrip.dailyBudgetFen;
      return {
        dayPlanId: day.id,
        date: day.date,
        plannedFen,
        remainingFen: demoTrip.dailyBudgetFen == null ? null : demoTrip.dailyBudgetFen - plannedFen,
        ratio,
        status: ratio === null ? "unconstrained" as const : ratio > 1 ? "over" as const : ratio >= 0.8 ? "watch" as const : "comfortable" as const,
      };
    });
    const totalPlannedFen = days.reduce((total, day) => total + day.plannedFen, 0);
    return {
      tripId,
      totalPlannedFen,
      totalRemainingFen: demoTrip.totalBudgetFen == null ? null : demoTrip.totalBudgetFen - totalPlannedFen,
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
      importance: "normal",
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
    if (input.importance !== undefined) activity.importance = input.importance;
    if (input.canSkip !== undefined) activity.canSkip = input.canSkip;
    if (input.minimumDurationMinutes !== undefined) activity.minimumDurationMinutes = input.minimumDurationMinutes;
    if (activity.importance === "must_do") activity.canSkip = false;
    if (activity.minimumDurationMinutes != null && activity.minimumDurationMinutes > activity.durationMinutes) throw new Error("最少停留时间不能超过停留时长");
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

  async createPlanningRun(tripId: string, userRequest: string): Promise<PlanningRun> {
    this.assertDemoTrip(tripId);
    const run = { id: `mock-run-${this.planningRuns.length + 1}`, tripId: DEMO_TRIP_UUID, runType: "replan" as const, status: "awaiting_confirmation" as const, userRequest, tokenUsage: 0, createdAt: new Date().toISOString() };
    this.planningRuns.unshift(run);
    return clone(run);
  }

  async listPlanningRuns(tripId: string): Promise<PlanningRun[]> {
    this.assertDemoTrip(tripId);
    return clone(this.planningRuns);
  }

  async getPlanningRun(): Promise<PlanningRun> {
    return { id: "mock-run", tripId: DEMO_TRIP_UUID, runType: "replan", status: "awaiting_confirmation", userRequest: "", tokenUsage: 0 };
  }

  async answerPlanningRun(_runId: string, answer: string): Promise<PlanningRun> {
    return { id: "mock-run", tripId: DEMO_TRIP_UUID, runType: "replan", status: "awaiting_confirmation", userRequest: answer, tokenUsage: 0 };
  }

  async decidePlanningRun(_runId: string, decision: "accept" | "reject"): Promise<{ run: PlanningRun; revision: PlanRevision }> {
    const run: PlanningRun = { id: "mock-run", tripId: DEMO_TRIP_UUID, runType: "replan", status: decision === "accept" ? "accepted" : "rejected", userRequest: "", tokenUsage: 0 };
    const revision = { ...(await this.getPlanRevision()), status: decision === "accept" ? "accepted" : "rejected" } as PlanRevision;
    return { run, revision };
  }

  async getPlanRevision(): Promise<PlanRevision> {
    return { id: "mock-revision", planningRunId: "mock-run", reason: "演示候选方案", activities: [], differenceSummary: {}, validationResult: {}, sourceIds: [], status: "pending" };
  }

  async acceptPlanRevision(): Promise<PlanRevision> {
    return { ...(await this.getPlanRevision()), status: "accepted" };
  }

  async rejectPlanRevision(): Promise<PlanRevision> {
    return { ...(await this.getPlanRevision()), status: "rejected" };
  }

  async getTripExecution(tripId: string): Promise<TripExecution> {
    this.assertDemoTrip(tripId);
    return clone(this.execution ?? this.buildExecution("not_started"));
  }

  async getExecutionProgress(tripId: string): Promise<import("../domain/types").ExecutionProgress> {
    const execution = await this.getTripExecution(tripId);
    return {
      tripId, itineraryVersion: 1, execution, navigationSession: null,
      currentActivityName: execution.activities.find((item) => item.activityId === execution.currentActivityId)?.name ?? null,
      currentActivityExperience: null, experienceImpact: null,
      navigationTargetName: null, riskLevel: "unknown", minimumDownstreamSlackMinutes: null,
      firstImpactedActivityId: null, activeDisruption: null, activeRecoveryRun: null,
      recoveryRevision: null, recoveryPlanning: null, generatedAt: new Date().toISOString(),
    };
  }

  async startTripExecution(tripId: string, dayPlanId?: string): Promise<TripExecution> {
    this.assertDemoTrip(tripId);
    if (!this.execution) {
      this.execution = this.buildExecution("in_progress", dayPlanId);
      this.execution.id = "mock-execution";
      this.execution.actualStartedAt = new Date().toISOString();
      this.execution.events.push({ id: "mock-event-start", eventType: "trip_started", occurredAt: new Date().toISOString(), details: {} });
      this.persistExecution();
    } else if (this.execution.status === "not_started") {
      this.execution.status = "in_progress";
      this.execution.id = "mock-execution";
      this.execution.actualStartedAt = new Date().toISOString();
      this.execution.events.push({ id: "mock-event-start", eventType: "trip_started", occurredAt: new Date().toISOString(), details: {} });
      this.persistExecution();
    }
    return clone(this.execution);
  }

  async applyTripExecutionAction(executionId: string, action: TripExecutionAction, activityId?: string): Promise<TripExecution> {
    if (!this.execution || this.execution.id !== executionId) throw new Error("旅行执行不存在");
    const now = new Date().toISOString();
    if (action === "pause") this.execution.status = "paused";
    else if (action === "resume") this.execution.status = "in_progress";
    else if (action === "finish") this.execution.status = "completed";
    else {
      const current = this.execution.activities.find((item) => item.activityId === (activityId ?? this.execution!.currentActivityId));
      if (!current) throw new Error("当前活动不存在");
      if (action === "arrive") { current.status = "arrived"; current.actualArrivedAt = now; }
      if (action === "start_activity") { current.status = "in_progress"; current.actualStartedAt = now; }
      if (action === "complete" || action === "skip") {
        current.status = action === "complete" ? "completed" : "skipped";
        current.actualEndedAt = now;
        const next = this.execution.activities.find((item) => item.status === "pending");
        this.execution.currentActivityId = next?.activityId;
        this.execution.currentDayPlanId = next?.dayPlanId;
        if (next) this.execution.currentDate = next.dayDate;
      }
    }
    this.execution.events.push({ id: `mock-event-${this.execution.events.length + 1}`, eventType: action, activityId, occurredAt: now, details: {} });
    const remaining = this.execution.activities.filter((item) => item.dayDate === this.execution!.currentDate && !["completed", "skipped"].includes(item.status));
    this.execution.remainingActivityCount = remaining.length;
    this.execution.remainingEstimatedCostFen = remaining.reduce((sum, item) => sum + item.estimatedCostFen, 0);
    this.persistExecution();
    return clone(this.execution);
  }

  async extendStay(): Promise<void> { /* The mock does not synthesize server-owned experience projections. */ }
  async leaveEarly(activityExecutionId: string): Promise<void> {
    if (!this.execution?.id) throw new Error("旅行执行不存在");
    const current = this.execution.activities.find((item) => item.id === activityExecutionId);
    if (current) await this.applyTripExecutionAction(this.execution.id, "complete", current.activityId);
  }

  async requestDynamicReplan(tripId: string, trigger: DynamicReplanTrigger, details: string): Promise<PlanningRun> {
    this.assertDemoTrip(tripId);
    if (!this.execution || !["in_progress", "paused"].includes(this.execution.status)) throw new Error("只有进行中的旅行可以动态重规划");
    const now = new Date().toISOString();
    this.execution.events.push({ id: `mock-event-${this.execution.events.length + 1}`, eventType: trigger, occurredAt: now, details: { source: "dynamic_replan", details } });
    const run: PlanningRun = { id: `mock-run-${this.planningRuns.length + 1}`, tripId, runType: "replan", status: "awaiting_confirmation", userRequest: details, tokenUsage: 0, createdAt: now };
    this.planningRuns.unshift(run);
    this.persist();
    return clone(run);
  }

  async resetDemo(): Promise<void> {
    this.days = clone(demoDays);
    this.execution = null;
    this.storage.removeItem(DEMO_EXECUTION_STORAGE_KEY);
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

  private buildExecution(status: TripExecution["status"], dayPlanId?: string): TripExecution {
    const startDay = this.days.find((day) => day.id === dayPlanId) ?? this.days[0];
    const activities = this.days.flatMap((day) => day.activities.map((activity) => ({
      activityId: activity.id, dayPlanId: day.id, dayDate: day.date, name: activity.name,
      scheduledTime: activity.scheduledTime, estimatedCostFen: activity.estimatedCostFen,
      status: "pending" as const, delayMinutes: 0,
    })));
    const current = activities.find((item) => item.dayPlanId === startDay.id);
    const remaining = activities.filter((item) => item.dayPlanId === startDay.id);
    return {
      tripId: DEMO_TRIP_UUID, status, currentDate: startDay.date, currentDayPlanId: startDay.id,
      currentActivityId: current?.activityId, scheduleDelayMinutes: 0,
      remainingActivityCount: remaining.length,
      remainingEstimatedCostFen: remaining.reduce((sum, item) => sum + item.estimatedCostFen, 0),
      activities, events: [],
    };
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

  private loadExecution(): TripExecution | null {
    try {
      const raw = this.storage.getItem(DEMO_EXECUTION_STORAGE_KEY);
      return raw ? JSON.parse(raw) as TripExecution : null;
    } catch {
      return null;
    }
  }

  private persistExecution() {
    if (this.execution) this.storage.setItem(DEMO_EXECUTION_STORAGE_KEY, JSON.stringify(this.execution));
  }

  private persist() {
    const state: PersistedDemoState = { version: DEMO_SCHEMA_VERSION, days: this.days };
    this.storage.setItem(DEMO_STORAGE_KEY, JSON.stringify(state));
  }
}
