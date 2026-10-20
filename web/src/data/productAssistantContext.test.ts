import { afterEach, describe, expect, it, vi } from "vitest";
import { productAssistantContext } from "./productAssistantContext";
import type { ExplorePlace } from "../domain/explore";

describe("C line assistant context boundary", () => {
  it("leaves the free assistant city omitted so follow-up requests retain server context", () => {
    expect(productAssistantContext({ surface: "assistant" }, "assistant-context-v1").context).not.toHaveProperty("browsing_city");
    expect(productAssistantContext({ city: "南京" }, "assistant-context-v1").context).toHaveProperty("browsing_city", "南京");
  });
  it("carries canonical identity without action permission or inferred GPS", () => {
    const place = { id: "53283e50-7288-4727-a05c-9515e8268ea2", city: "杭州市" } as ExplorePlace;
    expect(productAssistantContext({ place }, "assistant-context-v1")).toEqual({ context: {
      version: "assistant-context-v1", topic_id: "travel-main", surface: "place",
      browsing_city: "杭州市", discussing_place_id: place.id, read_trip_id: null,
      physical_location: null, action_target: null,
    } });
  });
  it("clears prior place context when discussing a Trip", () => {
    expect(productAssistantContext({ tripId: "trip-1" }, "assistant-context-v1").context)
      .toMatchObject({ surface: "trip", read_trip_id: "trip-1", discussing_place_id: null, action_target: null });
  });
  it("does not invent UUIDs for old Provider identities", () => {
    expect(() => productAssistantContext({ place: { id: "amap:B001" } as ExplorePlace }, "assistant-context-v1"))
      .toThrow("地点身份尚未接入");
  });
});


afterEach(() => { vi.unstubAllEnvs(); localStorage.clear(); });
it('sends comparison identities and filters without client place facts or action authority', () => {
 vi.stubEnv('VITE_DISCOVERY_PRODUCT','true');
 const places=[{id:'53283e50-7288-4727-a05c-9515e8268ea2',name:'不信任客户端事实',rating:5,city:'成都'} as ExplorePlace];
 const value=productAssistantContext({places,city:'成都',discovery:{center:{longitude:104,latitude:30,coordinate_system:'gcj02'},radius_meters:1000,category:'food',include_unknown:false,min_rating:4}},'assistant-context-v1').context!;
 expect(value).toMatchObject({discussing_place_ids:[places[0].id],discovery_context:{radius_meters:1000,category:'food',min_rating:4,include_unknown:false},read_trip_id:null,read_draft_id:null,physical_location:null,action_target:null});
 expect(JSON.stringify(value)).not.toContain('不信任客户端事实');
 expect(productAssistantContext({},'assistant-context-v1').context).toMatchObject({discussing_place_ids:[],discovery_context:null,read_draft_id:null});
});
it('reads saved drafts by identity and version without accepting client plan prose', () => {
 const value=productAssistantContext({draftContext:{draftId:'53283e50-7288-4727-a05c-9515e8268ea2',version:3,city:'成都',requirements:'客户端文字',plan:{untrusted:'客户端伪造'} }},'assistant-context-v1');
 expect(value.context).toMatchObject({surface:'draft',read_draft_version:3,action_target:null});
 expect(JSON.stringify(value)).not.toContain('客户端');
});
