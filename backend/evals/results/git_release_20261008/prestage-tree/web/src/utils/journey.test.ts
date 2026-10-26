import { defaultDayId, tripPhase } from "./journey";
import { demoTrip } from "../data/demoData";
import type { DayPlan } from "../domain/types";

it("derives dates inclusively and preserves archives without execution controls", () => {
  const trip = { ...demoTrip, startDate: "2026-09-08", endDate: "2026-09-10" };
  expect(tripPhase(trip, "2026-09-07")).toBe("upcoming");
  expect(tripPhase(trip, "2026-09-08")).toBe("active");
  expect(tripPhase(trip, "2026-09-10")).toBe("active");
  expect(tripPhase(trip, "2026-09-11")).toBe("completed");
  expect(tripPhase({ ...trip, status: "archived" }, "2026-09-08")).toBe("archived");
});

it("opens today's date, falling back to first date outside the trip", () => {
  const days = [{ id: "first", date: "2026-09-08" }, { id: "today", date: "2026-09-09" }] as DayPlan[];
  expect(defaultDayId(days, "2026-09-09")).toBe("today");
  expect(defaultDayId(days, "2026-10-01")).toBe("first");
  expect(defaultDayId([], "2026-09-09")).toBeNull();
});
