export type ExploreCategory = "all" | "sight" | "food" | "hotel";
export interface ExplorePoint { longitude: number; latitude: number; coordinate_system: "gcj02" }
export interface ExplorePhoto { url: string; title: string; source_url: string; attribution: string; thumbnail_url?: string; license_name?: string; license_url?: string; changes?: string; provider?: string; reviewed_at?: string }
export interface ReviewedExperience { summary: string; attributes: string[]; source_url: string; source_title: string; reviewed_at: string; confidence: string; usage_basis: string; unknown: string[]; scope: string }
export interface ExplorePlace {
  id: string; provider: "amap"; provider_place_id: string; name: string;
  category: Exclude<ExploreCategory, "all"> | "other"; city: string; address: string;
  location: ExplorePoint; rating: number | null; reference_cost_yuan: number | null;
  price_status: "reference" | "unknown"; photos: ExplorePhoto[];
  source_url: string; retrieved_at: string; description: string | null; phone: string | null;
  freshness?: "fresh" | "stale"; favorite?: boolean;
  image_status?: "available" | "missing" | "withheld_pending_license";
  identity_status?: string;
  aliases?: string[];
  recommendation_reasons?: string[];
  experience?: ReviewedExperience | null;
}
export interface ExploreResults { items: ExplorePlace[]; fetched_at: string; source: string }
export interface ExploreRoute {
  provider: string; mode: "walk" | "driving" | "transit";
  distance_meters: number; duration_seconds: number; path: number[][];
  origin: ExplorePoint; destination: ExplorePoint; destination_place_id: string;
  external_url: string; retrieved_at: string; is_estimated: false;
}
export interface ExploreSearch {
  city: string; q?: string; category?: ExploreCategory;
  near?: string; radius?: number;
}
export interface DiscoveryFilters { center?: ExplorePoint; radius?: number; min_rating?: number; max_food_price_yuan?: number; include_unknown?: boolean; use_preferences?: boolean }
export interface ExploreRepository {
  discover?(input: ExploreSearch, filters: DiscoveryFilters, signal?: AbortSignal): Promise<ExploreResults>;
  readonly routeModes?: ExploreRoute["mode"][];
  search(input: ExploreSearch, signal?: AbortSignal): Promise<ExploreResults>;
  detail(id: string, signal?: AbortSignal): Promise<ExplorePlace>;
  favorites(signal?: AbortSignal): Promise<ExploreResults>;
  favorite(id: string, value: boolean): Promise<void>;
  route(id: string, origin: ExplorePoint, mode: ExploreRoute["mode"]): Promise<ExploreRoute>;
}
