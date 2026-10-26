import { demoDays } from "../data/demoData";
import { buildRouteLegs, calculateBudget } from "./planner";

describe("planner calculations", () => {
  it("calculates a deterministic daily budget", () => {
    const summary = calculateBudget(demoDays[0].activities, 60_000);
    expect(summary.plannedFen).toBe(8_000);
    expect(summary.remainingFen).toBe(52_000);
    expect(summary.status).toBe("comfortable");
  });

  it("marks overspending and never relies on floating yuan values", () => {
    const expensive = demoDays[0].activities.map((activity) => ({ ...activity, estimatedCostFen: 30_001 }));
    const summary = calculateBudget(expensive, 60_000);
    expect(summary.plannedFen).toBe(90_003);
    expect(summary.status).toBe("over");
  });

  it("builds route legs in timeline order", () => {
    const legs = buildRouteLegs(demoDays[0].activities);
    expect(legs).toHaveLength(2);
    expect(legs[0].fromActivityId).toBe("activity-west-lake");
    expect(legs[0].toActivityId).toBe("activity-china-art-academy");
    expect(legs[0].distanceMeters).toBeGreaterThan(0);
  });
});
