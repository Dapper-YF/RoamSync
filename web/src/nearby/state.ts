import { useEffect, useState } from "react";
import type { ExploreCategory, ExplorePlace, ExplorePoint, ExploreResults } from "../domain/explore";

export interface NearbyQuery {
  city: string; query: string; category: ExploreCategory;
  center: ExplorePoint; radius_meters: number; min_rating?: number;
  max_food_price_yuan?: number; include_unknown: boolean;
}
export interface NearbyState {
  cityInput: string; city: string; centerInput: string; center?: ExplorePoint; centerName: string;
  query: string; category: ExploreCategory; radius: number; rating: string; price: string; includeUnknown: boolean;
  results?: ExploreResults; applied?: NearbyQuery; selected?: string; compared: ExplorePlace[];
  view: "split" | "list"; mapView?: { center: ExplorePoint; zoom: number }; mapRevision: number;
  compareOpen: boolean; scroll: number;
}
const initial: NearbyState = { cityInput: "", city: "", centerInput: "", centerName: "", query: "", category: "all", radius: 3000, rating: "", price: "", includeUnknown: true, compared: [], view: "split", mapRevision: 0, compareOpen: false, scroll: 0 };
export const nearbyStorageKey = "roamsync.nearby.v1";
export function useNearbyState() {
  const [state, setState] = useState<NearbyState>(() => {
    try { return { ...initial, ...JSON.parse(sessionStorage.getItem(nearbyStorageKey) || "{}") }; }
    catch { return initial; }
  });
  useEffect(() => { try { sessionStorage.setItem(nearbyStorageKey, JSON.stringify(state)); } catch { /* In-memory browsing still works. */ } }, [state]);
  return [state, (patch: Partial<NearbyState>) => setState(s => ({ ...s, ...patch }))] as const;
}
export function distanceMeters(a: ExplorePoint, b: ExplorePoint) {
  const r = Math.PI / 180, dlat = (b.latitude - a.latitude) * r, dlng = (b.longitude - a.longitude) * r;
  const h = Math.sin(dlat / 2) ** 2 + Math.cos(a.latitude * r) * Math.cos(b.latitude * r) * Math.sin(dlng / 2) ** 2;
  return Math.round(6371000 * 2 * Math.asin(Math.min(1, Math.sqrt(h))));
}
export function distanceLabel(m: number) { return m >= 1000 ? `${(m / 1000).toFixed(1)}公里` : `${m}米`; }

// Browser geolocation is WGS84. AMap POIs, maps and routes use GCJ02.
// Outside the supported GCJ02 service area fail closed instead of inventing a location.
export function wgs84ToGcj02(lng: number, lat: number): ExplorePoint {
  if (!Number.isFinite(lng) || !Number.isFinite(lat) || Math.abs(lng) > 180 || Math.abs(lat) > 90) throw Error("定位没有返回有效坐标，请改用手动选点。");
  if (lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271) throw Error("当前定位超出此地图服务的支持区域，请手动选择受支持城市。");
  const x = lng - 105, y = lat - 35, pi = Math.PI;
  let dlat = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
  dlat += (20 * Math.sin(6 * x * pi) + 20 * Math.sin(2 * x * pi)) * 2 / 3;
  dlat += (20 * Math.sin(y * pi) + 40 * Math.sin(y * pi / 3)) * 2 / 3;
  dlat += (160 * Math.sin(y * pi / 12) + 320 * Math.sin(y * pi / 30)) * 2 / 3;
  let dlng = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
  dlng += (20 * Math.sin(6 * x * pi) + 20 * Math.sin(2 * x * pi)) * 2 / 3;
  dlng += (20 * Math.sin(x * pi) + 40 * Math.sin(x * pi / 3)) * 2 / 3;
  dlng += (150 * Math.sin(x * pi / 12) + 300 * Math.sin(x * pi / 30)) * 2 / 3;
  const radlat = lat / 180 * pi, magic = 1 - 0.00669342162296594323 * Math.sin(radlat) ** 2, sqrtmagic = Math.sqrt(magic);
  dlat = dlat * 180 / ((6378245 * (1 - 0.00669342162296594323)) / (magic * sqrtmagic) * pi);
  dlng = dlng * 180 / (6378245 / sqrtmagic * Math.cos(radlat) * pi);
  return { longitude: lng + dlng, latitude: lat + dlat, coordinate_system: "gcj02" };
}
