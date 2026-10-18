import type { ExplorePlace, ExplorePoint, ExploreRepository, ExploreResults, ExploreRoute, ExploreSearch } from "../domain/explore";
import { PlaceContentRepository } from "./placeContentRepository";

export function createExploreRepository(): ExploreRepository {
  return import.meta.env.VITE_TRAVEL_CONTENT_CONTRACT === "place-content-v1" ? new PlaceContentRepository() : new ApiExploreRepository();
}

// Legacy preview only supplied attribution. It does not establish image usage rights.
function previewPlace(place: ExplorePlace): ExplorePlace {
  return { ...place, photos: [], image_status: place.photos.length ? "withheld_pending_license" : "missing" };
}

export class ApiExploreRepository implements ExploreRepository {
  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`/api/v1/explore${path}`, init);
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      const detail = error.detail;
      throw new Error(typeof detail === "string" ? detail : detail?.message ?? "暂时无法获取旅游信息，请稍后重试");
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }
  async search(input: ExploreSearch, signal?: AbortSignal) {
    const params = new URLSearchParams({ city: input.city, category: input.category ?? "all" });
    if (input.q) params.set("q", input.q);
    if (input.near) params.set("near", input.near);
    if (input.radius) params.set("radius", String(input.radius));
    const result = await this.request<ExploreResults>(`/places?${params}`, { signal });
    return { ...result, items: result.items.map(previewPlace) };
  }
  async detail(id: string, signal?: AbortSignal) { return previewPlace(await this.request<ExplorePlace>(`/places/${encodeURIComponent(id)}`, { signal })); }
  async favorites(signal?: AbortSignal) {
    const result = await this.request<ExploreResults>("/favorites", { signal });
    return { ...result, items: result.items.map(previewPlace) };
  }
  async favorite(id: string, value: boolean) {
    await this.request(`/favorites/${encodeURIComponent(id)}`, { method: value ? "PUT" : "DELETE" });
  }
  route(id: string, origin: ExplorePoint, mode: ExploreRoute["mode"]) {
    return this.request<ExploreRoute>("/routes", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ origin, destination_place_id: id, mode }),
    });
  }
}
