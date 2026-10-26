import type { Activity, BudgetSummary, Fen, RouteLeg } from "../domain/types";

export const formatFen = (fen: Fen) =>
  new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(fen / 100);

export function calculateBudget(activities: Activity[], dailyBudgetFen: Fen): BudgetSummary {
  const plannedFen = activities.reduce((total, activity) => total + activity.estimatedCostFen, 0);
  const remainingFen = dailyBudgetFen - plannedFen;
  const ratio = dailyBudgetFen === 0 ? 1 : plannedFen / dailyBudgetFen;
  return {
    plannedFen,
    remainingFen,
    ratio,
    status: ratio > 1 ? "over" : ratio >= 0.8 ? "watch" : "comfortable",
  };
}

export function buildRouteLegs(activities: Activity[]): RouteLeg[] {
  return activities.slice(0, -1).map((activity, index) => {
    const next = activities[index + 1];
    const distanceMeters = Math.round(haversineMeters(activity.coordinates, next.coordinates));
    const mode = distanceMeters <= 1800 ? "walk" : "transit";
    const speedMetersPerMinute = mode === "walk" ? 75 : 260;
    return {
      fromActivityId: activity.id,
      toActivityId: next.id,
      durationMinutes: Math.max(6, Math.round(distanceMeters / speedMetersPerMinute)),
      distanceMeters,
      mode,
      provider: "Mock route",
      isEstimated: true,
    };
  });
}

function haversineMeters(a: readonly [number, number], b: readonly [number, number]) {
  const earthRadius = 6_371_000;
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
  const latitudeDelta = toRadians(b[1] - a[1]);
  const longitudeDelta = toRadians(b[0] - a[0]);
  const latitudeA = toRadians(a[1]);
  const latitudeB = toRadians(b[1]);
  const h =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(latitudeA) * Math.cos(latitudeB) * Math.sin(longitudeDelta / 2) ** 2;
  return 2 * earthRadius * Math.asin(Math.sqrt(h));
}
