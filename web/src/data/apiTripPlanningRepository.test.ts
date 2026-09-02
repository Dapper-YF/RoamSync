import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError, ApiTripPlanningRepository } from "./apiTripPlanningRepository";
import { DEMO_TRIP_UUID } from "./demoData";

describe("ApiTripPlanningRepository", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("maps snake_case trip DTOs using the real trip UUID", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      id: DEMO_TRIP_UUID,
      title: "杭州 · 两日慢游",
      destination: "杭州",
      accommodation: "湖滨",
      start_date: "2026-09-05",
      end_date: "2026-09-06",
      total_budget_fen: 120000,
      daily_budget_fen: 60000,
      currency: "CNY",
      destination_adcode: "330100",
      destination_citycode: "0571",
      center_longitude: 120.1551,
      center_latitude: 30.2562,
      accommodation_poi_id: "",
      accommodation_longitude: null,
      accommodation_latitude: null,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const trip = await new ApiTripPlanningRepository().getTrip(DEMO_TRIP_UUID);
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/trips/${DEMO_TRIP_UUID}`, undefined);
    expect(trip.startDate).toBe("2026-09-05");
    expect(trip.totalBudgetFen).toBe(120000);
    expect(trip.destinationAdcode).toBe("330100");
  });

  it("maps real AMap city suggestions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify([{
      name: "南昌市", adcode: "360100", citycode: "0791", longitude: 115.857972, latitude: 28.682976,
    }]), { status: 200, headers: { "Content-Type": "application/json" } })));
    const cities = await new ApiTripPlanningRepository().searchCities("南昌");
    expect(cities[0]).toEqual({ name: "南昌市", adcode: "360100", citycode: "0791", coordinates: [115.857972, 28.682976] });
  });

  it("maps and updates the structured planning profile", async () => {
    const dto = {
      trip_id: DEMO_TRIP_UUID,
      pace: "relaxed",
      interest_categories: ["history", "food"],
      transport_modes: ["walk", "transit"],
      daily_start_time: "09:30:00",
      daily_end_time: "20:30:00",
      meal_preferences: "不吃辣",
      avoid_categories: ["大型乐园"],
      max_walking_minutes: 45,
      free_text_requirements: "下午保留机动时间",
      version: 2,
      updated_at: "2026-09-02T01:00:00Z",
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(dto), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...dto, version: 3 }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const repository = new ApiTripPlanningRepository();

    const preferences = await repository.getTripPreferences(DEMO_TRIP_UUID);
    expect(preferences).toMatchObject({ pace: "relaxed", dailyStartTime: "09:30", maxWalkingMinutes: 45 });
    const updated = await repository.updateTripPreferences(DEMO_TRIP_UUID, preferences);
    expect(updated.version).toBe(3);
    expect(JSON.parse(fetchMock.mock.calls[1][1]?.body as string)).toMatchObject({
      interest_categories: ["history", "food"],
      daily_start_time: "09:30",
      max_walking_minutes: 45,
    });
  });

  it("returns the server-generated activity id after adding a place", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      id: "activity-id",
      place_id: "place-id",
      name: "雷峰塔",
      category: "sight",
      neighborhood: "南山路",
      longitude: 120.14852,
      latitude: 30.23111,
      scheduled_time: "20:05:00",
      duration_minutes: 75,
      estimated_cost_fen: 4000,
      status: "planned",
      position: 3,
      note: null,
      source: {
        id: "source-id",
        title: "雷峰塔景区",
        url: "https://example.com",
        provider: "高德地图",
        queried_at: "2026-08-31T02:00:00Z",
        confidence: "high",
      },
    }), { status: 201, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const activity = await new ApiTripPlanningRepository().addActivity("day-id", "place-id");
    expect(activity.id).toBe("activity-id");
    expect(activity.scheduledTime).toBe("20:05");
  });

  it("surfaces API error details", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: "place is already in this trip" }),
      { status: 409, headers: { "Content-Type": "application/json" } },
    )));
    await expect(new ApiTripPlanningRepository().addActivity("day", "place")).rejects.toEqual(
      new ApiRequestError(409, "place is already in this trip"),
    );
  });

  it("surfaces structured map provider error messages", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ detail: { code: "map_quota_exceeded", message: "高德免费配额已用尽" } }),
      { status: 429, headers: { "Content-Type": "application/json" } },
    )));
    await expect(new ApiTripPlanningRepository().searchPlaces(DEMO_TRIP_UUID, "景点")).rejects.toEqual(
      new ApiRequestError(429, "高德免费配额已用尽"),
    );
  });

  it("maps persisted route legs and sends server-side place searches", async () => {
    const dayDto = {
      id: "day-id", trip_id: DEMO_TRIP_UUID, date: "2026-09-05", label: "第 1 天", theme: "湖滨", position: 0,
      activities: [],
      route_legs: [{
        id: "leg", from_activity_id: "a", to_activity_id: "b", position: 0, mode: "driving",
        distance_meters: 1500, duration_minutes: 6, provider: "AMap Route 2.0", is_estimated: false,
        path: [[115.8, 28.6], [115.9, 28.7]],
        alternatives: [{ distance_meters: 1700, duration_minutes: 7, path: [[115.8, 28.6], [115.85, 28.65], [115.9, 28.7]] }],
      }],
      conflicts: [{ activity_id: "b", code: "late_finish", message: "将在 22:00 后结束" }],
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(dayDto), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify([{
        provider: "amap", provider_place_id: "B_MUSEUM", name: "博物馆", category: "culture",
        neighborhood: "东湖区", description: "城市博物馆", longitude: 115.9, latitude: 28.7,
        suggested_duration_minutes: 120, estimated_cost_fen: 0, rating: 4.6,
        tags: ["博物馆"], source_url: "https://www.amap.com/search?id=B_MUSEUM",
      }]), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const repository = new ApiTripPlanningRepository();

    const day = await repository.recalculateRoute("day-id", "driving");
    expect(day.routeLegs?.[0]).toMatchObject({
      mode: "driving", provider: "AMap Route 2.0", isEstimated: false,
      path: [[115.8, 28.6], [115.9, 28.7]],
      alternatives: [{ distanceMeters: 1700, durationMinutes: 7 }],
    });
    expect(day.conflicts?.[0].code).toBe("late_finish");
    const places = await repository.searchPlaces(DEMO_TRIP_UUID, "博物馆", "culture");
    expect(fetchMock.mock.calls[1][0]).toContain(`/api/v1/trips/${DEMO_TRIP_UUID}/places/search?q=`);
    expect(fetchMock.mock.calls[1][0]).toContain("category=culture");
    expect(places[0]).toMatchObject({ kind: "search", providerPoiId: "B_MUSEUM", name: "博物馆" });
  });

  it("persists a transient POI snapshot only when adding it", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      id: "activity-id", place_id: "persisted-place-id", name: "滕王阁", category: "culture",
      neighborhood: "东湖区", longitude: 115.881, latitude: 28.683, scheduled_time: "09:00:00",
      duration_minutes: 120, estimated_cost_fen: 5000, status: "planned", position: 0, note: null,
      source: { id: "source-id", title: "高德地点搜索：滕王阁", url: "https://www.amap.com/search?id=B_TWG", provider: "AMap POI", queried_at: "2026-09-01T00:00:00Z", confidence: "high" },
    }), { status: 201, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    await new ApiTripPlanningRepository().addActivity("day-id", {
      kind: "search", provider: "amap", providerPoiId: "B_TWG", name: "滕王阁", category: "culture",
      neighborhood: "东湖区", description: "沿江古迹", coordinates: [115.881, 28.683],
      suggestedDurationMinutes: 120, estimatedCostFen: 5000, rating: 4.8, tags: ["景点"],
      sourceUrl: "https://www.amap.com/search?id=B_TWG",
    });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const body = JSON.parse(String(init.body));
    expect(body.place_id).toBeUndefined();
    expect(body.place_snapshot).toMatchObject({ provider_place_id: "B_TWG", name: "滕王阁" });
  });

  it("maps and updates editable activity fields with optimistic versioning", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      id: "activity-id", place_id: "place-id", name: "滕王阁", custom_name: "滕王阁日落",
      display_name: "滕王阁日落", category: "culture", neighborhood: "东湖区",
      longitude: 115.881, latitude: 28.683, scheduled_time: "17:30:00", duration_minutes: 120,
      estimated_cost_fen: 5000, status: "planned", position: 0, schedule_locked: true,
      version: 2, note: "提前购票", updated_at: "2026-09-01T12:00:00Z",
      source: { id: "source-id", title: "滕王阁", url: "https://www.amap.com/search?id=B_TWG", provider: "AMap POI", queried_at: "2026-09-01T00:00:00Z", confidence: "high" },
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const activity = await new ApiTripPlanningRepository().updateActivity("activity-id", {
      version: 1,
      customName: "滕王阁日落",
      scheduledTime: "17:30",
      durationMinutes: 120,
      estimatedCostFen: 5000,
      note: "提前购票",
      scheduleLocked: true,
    });
    expect(activity).toMatchObject({
      name: "滕王阁日落", originalName: "滕王阁", customName: "滕王阁日落",
      scheduleLocked: true, version: 2, updatedAt: "2026-09-01T12:00:00Z",
    });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toMatchObject({
      version: 1, custom_name: "滕王阁日落", scheduled_time: "17:30", schedule_locked: true,
    });
  });

  it("maps both day plans returned by a cross-day move", async () => {
    const activityDto = {
      id: "activity-id", place_id: "place-id", name: "滕王阁", custom_name: null,
      display_name: "滕王阁", category: "culture", neighborhood: "东湖区",
      longitude: 115.881, latitude: 28.683, scheduled_time: "09:00:00", duration_minutes: 120,
      estimated_cost_fen: 5000, status: "planned", position: 0, schedule_locked: false,
      version: 2, note: null, updated_at: "2026-09-02T00:00:00Z",
      source: { id: "source-id", title: "滕王阁", url: "https://www.amap.com/search?id=B_TWG", provider: "AMap POI", queried_at: "2026-09-01T00:00:00Z", confidence: "high" },
    };
    const day = (id: string, activities: typeof activityDto[]) => ({
      id, trip_id: DEMO_TRIP_UUID, date: "2026-09-05", label: id, theme: id, position: 0,
      route_mode: "walk", activities, route_legs: [], conflicts: [],
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      activity_id: "activity-id", source_day: day("day-1", []), target_day: day("day-2", [activityDto]),
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await new ApiTripPlanningRepository().moveActivity("activity-id", {
      version: 1, targetDayPlanId: "day-2", targetPosition: 0,
    });
    expect(result.targetDay.activities[0]).toMatchObject({ id: "activity-id", version: 2 });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ version: 1, target_day_plan_id: "day-2", target_position: 0 });
  });
});
