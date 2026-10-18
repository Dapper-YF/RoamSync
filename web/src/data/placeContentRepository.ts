import type { ExplorePhoto, ExplorePlace, ExplorePoint, ExploreRepository, ExploreResults, ExploreRoute, ExploreSearch, DiscoveryFilters, ReviewedExperience } from "../domain/explore";

export interface ContentImage { url: string; attribution: string; source_url: string; usage_basis: string; place_ref?: ContentPlace['ref'] | null; provider?: string | null; title?: string | null; thumbnail_url?: string | null; license_name?: string | null; license_url?: string | null; changes?: string | null; reviewed_at?: string | null }
export function approvedPhotos(images: ContentImage[], placeId: string, providerId?: string): ExplorePhoto[] {
  const asset = (url: string) => /^\/api\/v1\/media\/place-images\/[a-z0-9-]+\.jpg$/.test(url);
  return images.filter(photo => photo.usage_basis === 'reviewed_commons_license' && photo.provider === 'wikimedia_commons'
    && photo.place_ref?.place_id === placeId && photo.place_ref.external_ref.provider === 'amap'
    && (!providerId || photo.place_ref.external_ref.provider_place_id === providerId)
    && asset(photo.url) && !!photo.thumbnail_url && asset(photo.thumbnail_url)
    && photo.source_url.startsWith('https://commons.wikimedia.org/wiki/File:')
    && !!photo.license_name && /^https:\/\/creativecommons\.org\/(licenses\/by(-sa)?\/[\d.]+\/?|publicdomain\/zero\/1\.0(\/deed\.en)?\/?)$/.test(photo.license_url ?? '')
    && !!photo.attribution.trim()).map(photo => ({url:photo.url, title:photo.title ?? '', source_url:photo.source_url, attribution:photo.attribution,
      thumbnail_url:photo.thumbnail_url!, license_name:photo.license_name!, license_url:photo.license_url!, changes:photo.changes ?? '', provider:photo.provider!, reviewed_at:photo.reviewed_at ?? ''}));
}

// Boundary DTO mirrors B's place_content/contracts.py; internal UI keeps one view model.
export interface ContentPlace {
  ref: { place_id: string; external_ref: { provider: "amap"; provider_place_id: string } };
  name: string; category: "attraction" | "food" | "lodging" | "other";
  aliases?: string[];
  address: string | null; city: string | null; provider_type?: string | null;
  location: { longitude: number; latitude: number; coordinate_system: "GCJ02" };
  rating: number | null; price: null | { amount: number; currency: "CNY"; unit: "per_person_reference"; verified_live_quote: false };
  images: ContentImage[];
  image_status: "available" | "missing" | "withheld_pending_license";
  identity_status: string;
  experience?: ReviewedExperience | null;
  source: { provider: "amap"; source_url: string; fetched_at: string; freshness: "fresh" | "stale" };
}
export function toExplorePlace(place: ContentPlace): ExplorePlace {
  const category = ({ attraction: "sight", food: "food", lodging: "hotel", other: "other" } as const)[place.category];
  const price = category !== "hotel" ? place.price?.amount ?? null : null;
  return {
    id: place.ref.place_id, provider: place.ref.external_ref.provider,
    provider_place_id: place.ref.external_ref.provider_place_id, name: place.name,
    category, aliases: place.aliases ?? [], city: place.city ?? "", address: place.address ?? "",
    location: { ...place.location, coordinate_system: "gcj02" }, rating: place.rating,
    reference_cost_yuan: price, price_status: price == null ? "unknown" : "reference",
    photos: place.image_status === "available" ? approvedPhotos(place.images, place.ref.place_id, place.ref.external_ref.provider_place_id) : [],
    image_status: place.image_status, identity_status: place.identity_status, experience: place.experience,
    source_url: place.source.source_url, retrieved_at: place.source.fetched_at,
    freshness: place.source.freshness, description: place.provider_type ?? null, phone: null,
  };
}

export class PlaceContentRepository implements ExploreRepository {
  readonly routeModes: ExploreRoute["mode"][] = ["walk", "driving"];
  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`/api/v1${path}`, init);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === "string" ? body.detail : body.detail?.message ?? "旅游服务暂不可用，请稍后再试。");
    }
    return response.status === 204 ? undefined as T : response.json();
  }
  async discover(input: ExploreSearch, filters: DiscoveryFilters, signal?: AbortSignal): Promise<ExploreResults> {
    const category = input.category === "sight" ? "attraction" : input.category === "hotel" ? "lodging" : input.category === "food" ? "food" : null;
    const result = await this.request<{ items: Array<{ place: ContentPlace; reasons: string[] }> }>("/places/discover", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal,
      body: JSON.stringify({ city: input.city, query: input.q ?? "", category,
        center: filters.center ? { ...filters.center, coordinate_system: "GCJ02" } : null,
        radius_meters: filters.radius ?? 3000, min_rating: filters.min_rating ?? null,
        max_food_price_yuan: filters.max_food_price_yuan ?? null, include_unknown: filters.include_unknown ?? true,
        use_preferences: filters.use_preferences ?? true }),
    });
    return { items: result.items.map(({ place, reasons }) => ({ ...toExplorePlace(place), recommendation_reasons: reasons })),
      fetched_at: result.items[0]?.place.source.fetched_at ?? new Date().toISOString(), source: "高德地图 · 当前条件查询" };
  }
  async search(input: ExploreSearch, signal?: AbortSignal): Promise<ExploreResults> {
    const categories = !input.q && (!input.category || input.category === "all")
      ? ["attraction", "food", "lodging"]
      : [input.category === "sight" ? "attraction" : input.category === "hotel" ? "lodging" : input.category === "food" ? "food" : undefined];
    const responses = await Promise.all(categories.map((category) => {
      const params = new URLSearchParams({ city: input.city, query: input.q ?? "", page_size: categories.length > 1 ? "4" : "12" });
      if (category) params.set("category", category);
      if (input.near) {
        const [longitude, latitude] = input.near.split(",");
        params.set("longitude", longitude); params.set("latitude", latitude); params.set("coordinate_system", "GCJ02");
      }
      if (input.radius) params.set("radius_meters", String(input.radius));
      return this.request<{ items: ContentPlace[] }>(`/places/search?${params}`, { signal });
    }));
    return this.results([...new Map(responses.flatMap((result) => result.items).map((place) => [place.ref.place_id, place])).values()]);
  }
  async detail(id: string, signal?: AbortSignal) { return toExplorePlace(await this.request<ContentPlace>(`/places/${encodeURIComponent(id)}`, { signal })); }
  async favorites(signal?: AbortSignal) {
    const items = await this.request<Array<{ place: ContentPlace }>>("/me/favorites", { signal });
    return this.results(items.map((item) => item.place));
  }
  async favorite(id: string, value: boolean) { await this.request(`/me/favorites/${encodeURIComponent(id)}`, { method: value ? "PUT" : "DELETE" }); }
  async route(id: string, origin: ExplorePoint, mode: ExploreRoute["mode"]): Promise<ExploreRoute> {
    if (mode === "transit") throw new Error("当前路线服务支持步行与驾车。");
    const place = await this.detail(id);
    const result = await this.request<{ distance_meters: number; duration_seconds: number; path: ContentPlace["location"][]; source: ContentPlace["source"] }>("/routes/query", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origin: { ...origin, coordinate_system: "GCJ02" }, destination: { ...place.location, coordinate_system: "GCJ02" }, mode }),
    });
    const params = new URLSearchParams({ from: `${origin.longitude},${origin.latitude},出发位置`, to: `${place.location.longitude},${place.location.latitude},${place.name}`, mode: mode === "walk" ? "walk" : "car", src: "RoamSync", coordinate: "gaode", callnative: "1" });
    return { provider: result.source.provider, mode, origin, destination: place.location, destination_place_id: id,
      distance_meters: result.distance_meters, duration_seconds: result.duration_seconds,
      path: result.path.map((point) => [point.longitude, point.latitude]),
      external_url: `https://uri.amap.com/navigation?${params}`, retrieved_at: result.source.fetched_at, is_estimated: false };
  }
  private results(items: ContentPlace[]): ExploreResults {
    return { items: items.map(toExplorePlace), fetched_at: items[0]?.source.fetched_at ?? new Date().toISOString(), source: "高德地图地点服务" };
  }
}
