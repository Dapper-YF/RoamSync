import { afterEach, expect, it, vi } from "vitest";
import { PlaceContentRepository, toExplorePlace, type ContentPlace } from "./placeContentRepository";

// Synthetic contract fixture v1, used only by tests; never served to the product.
const fixture: { version: 1; synthetic: true; place: ContentPlace } = {
  version: 1, synthetic: true, place: {
    ref: { place_id: "53283e50-7288-4727-a05c-9515e8268ea2", external_ref: { provider: "amap", provider_place_id: "SYNTHETIC_ONLY" } },
    name: "合成测试地点", category: "food", address: null, city: "杭州市",
    location: { longitude: 120.15, latitude: 30.25, coordinate_system: "GCJ02" }, rating: null,
    price: { amount: 88, currency: "CNY", unit: "per_person_reference", verified_live_quote: false },
    images: [{ url: "https://example.test/photo.jpg", source_url: "https://example.test/source", attribution: "synthetic", usage_basis: "" }],
    image_status: "withheld_pending_license", identity_status: "provider_identity",
    source: { provider: "amap", source_url: "https://example.test/source", fetched_at: "2026-10-15T00:00:00Z", freshness: "fresh" },
  },
};
afterEach(() => vi.unstubAllGlobals());

it("preserves canonical UUID and unknown facts while withholding unlicensed photos", () => {
  const place = toExplorePlace(fixture.place);
  expect(place.id).toBe(fixture.place.ref.place_id);
  expect(place.aliases).toEqual([]); // legacy payloads omit optional provider aliases
  expect(place.rating).toBeNull(); expect(place.address).toBe(""); expect(place.photos).toEqual([]);
  expect(place.reference_cost_yuan).toBe(88);
  expect(toExplorePlace({ ...fixture.place, category: "lodging" }).reference_cost_yuan).toBeNull();
});
it("passes provider aliases through as metadata without changing the canonical UUID", () => {
  const place = toExplorePlace({ ...fixture.place, aliases: ["风篁岭;供应商原文"] });
  expect(place.id).toBe(fixture.place.ref.place_id);
  expect(place.aliases).toEqual(["风篁岭;供应商原文"]);
});
it("requires an image usage basis even when availability is claimed", () => {
  expect(toExplorePlace({ ...fixture.place, image_status: "available" }).photos).toEqual([]);
});
it("maps B favorites without sending any client owner identity", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify([{ place: fixture.place, saved_at: "2026-10-15T00:00:00Z" }])))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetch);
  const repository = new PlaceContentRepository();
  expect((await repository.favorites()).items[0].id).toBe(fixture.place.ref.place_id);
  await repository.favorite(fixture.place.ref.place_id, false);
  expect(fetch).toHaveBeenLastCalledWith(`/api/v1/me/favorites/${fixture.place.ref.place_id}`, { method: "DELETE" });
});
it("converts route coordinates and offers external handoff without claiming navigation started", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(fixture.place)))
    .mockResolvedValueOnce(new Response(JSON.stringify({ distance_meters: 400, duration_seconds: 360,
      path: [fixture.place.location, { ...fixture.place.location, longitude: 120.16 }], source: fixture.place.source })));
  vi.stubGlobal("fetch", fetch);
  const route = await new PlaceContentRepository().route(fixture.place.ref.place_id, { longitude: 120.16, latitude: 30.25, coordinate_system: "gcj02" }, "walk");
  expect(route.path).toEqual([[120.15, 30.25], [120.16, 30.25]]);
  expect(route.external_url).toContain("https://uri.amap.com/navigation?");
  const body = JSON.parse(fetch.mock.calls[1][1].body);
  expect(body.origin.coordinate_system).toBe("GCJ02"); expect(body.destination.coordinate_system).toBe("GCJ02");
  expect(body).not.toHaveProperty("trip_id");
});

it("discovers from explicit GCJ02 point and filters without client owner identity", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [{ place: fixture.place, reasons: ["explicit preference"] }] })));
  vi.stubGlobal("fetch", fetch);
  const result = await new PlaceContentRepository().discover({ city: "Hangzhou", category: "food" }, {
    center: { longitude: 120.15, latitude: 30.25, coordinate_system: "gcj02" }, radius: 1000,
    min_rating: 4, max_food_price_yuan: 100, include_unknown: false,
  });
  expect(result.items[0].recommendation_reasons).toEqual(["explicit preference"]);
  expect(result.source).toBe("高德地图 · 当前条件查询");
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.center.coordinate_system).toBe("GCJ02"); expect(body.category).toBe("food");
  expect(body.radius_meters).toBe(1000); expect(body.include_unknown).toBe(false);
  expect(body).not.toHaveProperty("owner_id"); expect(body).not.toHaveProperty("trip_id");
});
