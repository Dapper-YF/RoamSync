import type { Activity } from "../domain/types";
import type { ExplorePoint } from "../domain/explore";

export interface RouteOrigin { point: ExplorePoint; name: string; activityId?: string }
export interface JourneyRouteResult {
  distance_meters: number; duration_seconds: number;
  path: Array<{ longitude: number; latitude: number; coordinate_system: "GCJ02" }>;
  source: { provider: string; fetched_at: string };
}
export function activityPoint(activity: Activity): ExplorePoint | null {
  // Formal Activity has no CRS field. These two server source values come from
  // planner_repository.ensure_place_candidate and draft_promotion.materialize:
  // both persist untransformed AMap coordinates. Unknown historical sources fail closed.
  if (!["amap", "amap poi"].includes(activity.source.provider.toLowerCase())) return null;
  const [longitude, latitude] = activity.coordinates;
  if (!Number.isFinite(longitude) || !Number.isFinite(latitude) || Math.abs(longitude) > 180 || Math.abs(latitude) > 90) return null;
  return { longitude, latitude, coordinate_system: "gcj02" };
}
export function safeReturnTo(value: string | null, tripId: string) {
  const fallback = `/trips/${encodeURIComponent(tripId)}`;
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u001f]/.test(value)) return fallback;
  try { const parsed = new URL(value, "https://local.invalid"); return parsed.origin === "https://local.invalid" ? `${parsed.pathname}${parsed.search}${parsed.hash}` : fallback; }
  catch { return fallback; }
}
export function externalRoute(origin: RouteOrigin, destination: ExplorePoint, name: string, mode: "walk" | "driving") {
  const query = new URLSearchParams({ from: `${origin.point.longitude},${origin.point.latitude},${origin.name}`,
    to: `${destination.longitude},${destination.latitude},${name}`, mode: mode === "walk" ? "walk" : "car",
    coordinate: "gaode", src: "RoamSync", callnative: "1" });
  return `https://uri.amap.com/navigation?${query}`;
}
export async function queryJourneyRoute(origin: ExplorePoint, destination: ExplorePoint, mode: "walk" | "driving"): Promise<JourneyRouteResult> {
  const response = await fetch("/api/v1/routes/query", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ origin: { ...origin, coordinate_system: "GCJ02" }, destination: { ...destination, coordinate_system: "GCJ02" }, mode }) });
  if (!response.ok) throw new Error("路线服务暂时不可用，请稍后重试。");
  return response.json();
}
