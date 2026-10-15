import { DEMO_SCHEMA_VERSION, DEMO_STORAGE_KEY, DEMO_TRIP_ID } from "./demoData";
import { LocalTripPlanningRepository } from "./mockTripPlanningRepository";

describe("LocalTripPlanningRepository", () => {
  beforeEach(() => localStorage.clear());

  it("adds, persists, reorders, and removes activities", async () => {
    const repository = new LocalTripPlanningRepository(localStorage);
    await repository.addActivity("day-1", "leifeng-pagoda");
    let days = await repository.getDays(DEMO_TRIP_ID);
    expect(days[0].activities.at(-1)?.placeId).toBe("leifeng-pagoda");

    const ids = days[0].activities.map((activity) => activity.id).reverse();
    await repository.reorderActivities("day-1", ids);
    days = await new LocalTripPlanningRepository(localStorage).getDays(DEMO_TRIP_ID);
    expect(days[0].activities.map((activity) => activity.id)).toEqual(ids);

    await repository.removeActivity("activity-leifeng-pagoda");
    const candidates = await repository.getCandidates(DEMO_TRIP_ID);
    expect(candidates.some((candidate) => candidate.id === "leifeng-pagoda")).toBe(true);
  });

  it("ignores persisted data with an incompatible schema version", async () => {
    localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify({ version: DEMO_SCHEMA_VERSION + 1, days: [] }));
    const days = await new LocalTripPlanningRepository(localStorage).getDays(DEMO_TRIP_ID);
    expect(days).toHaveLength(2);
    expect(days[0].activities.length).toBeGreaterThan(0);
  });

  it("restores the built-in demo", async () => {
    const repository = new LocalTripPlanningRepository(localStorage);
    await repository.removeActivity("activity-west-lake");
    await repository.resetDemo();
    const days = await repository.getDays(DEMO_TRIP_ID);
    expect(days[0].activities[0].placeId).toBe("west-lake");
  });

  it("records a travel event when requesting dynamic replanning", async () => {
    const repository = new LocalTripPlanningRepository(localStorage);
    const execution = await repository.startTripExecution(DEMO_TRIP_ID, "day-1");
    const run = await repository.requestDynamicReplan(DEMO_TRIP_ID, "delay", "当前活动延误 45 分钟");
    expect(run.status).toBe("awaiting_confirmation");
    const state = await repository.getTripExecution(DEMO_TRIP_ID);
    expect(state.events.at(-1)).toMatchObject({ eventType: "delay", details: { source: "dynamic_replan" } });
    expect(execution.id).toBeTruthy();
  });
});
