import type { DayPlan, Trip } from "../domain/types";

export function localDate(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

// Calendar display only; never changes the stored execution or activity records.
export function tripPhase(trip: Trip, today = localDate()): NonNullable<Trip["status"]> {
  if (trip.status === "archived" || trip.archivedAt) return "archived";
  if (today < trip.startDate) return "upcoming";
  if (today > trip.endDate) return "completed";
  return "active";
}

export function defaultDayId(days: DayPlan[], today = localDate()): string | null {
  return days.find((day) => day.date === today)?.id ?? days[0]?.id ?? null;
}

// Acceptance can bump versions and recreate routes on unchanged days. Compare
// visible plan content so a local revision opens the day that actually changed.
export function changedPlanDayIds(before: DayPlan[], after: DayPlan[]): string[] {
  const content = (day: DayPlan) => JSON.stringify({
    activities: day.activities.map((item) => [item.placeId, item.name, item.scheduledTime,
      item.durationMinutes, item.estimatedCostFen, item.status, item.scheduleLocked, item.note ?? ""]),
    mode: day.routeMode,
    routes: day.routeLegs?.map((leg) => [leg.mode, leg.durationMinutes, leg.distanceMeters]),
  });
  return after.filter((day) => {
    const previous = before.find((item) => item.id === day.id);
    return !previous || content(previous) !== content(day);
  }).map((day) => day.id);
}
