import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Activity, Trip } from "../domain/types";
import { JourneyRoutePage } from "./JourneyRoutePage";
import { activityPoint, safeReturnTo } from "./routeModel";

vi.mock("../product/ExploreMap", () => ({ ExploreMap: ({ onPickPoint }: { onPickPoint: (point: unknown) => void }) => <button onClick={() => onPickPoint({ longitude: 121, latitude: 31, coordinate_system: "gcj02" })}>地图点选起点</button> }));
const activity = (id: string, name: string): Activity => ({ id, name, coordinates: [120.1, 30.2], source: { provider: "AMap POI" } } as unknown as Activity);
const origin = activity("a1", "出发地点");
const destination = activity("a2", "正式目的地");
const repository = { getTrip: vi.fn(async () => ({ id: "trip", title: "成都旅行", destination: "成都" } as Trip)),
  getDays: vi.fn(async () => [{ id: "day", activities: [origin, destination] }]) };
function page(repo = repository) {
  return render(<MemoryRouter initialEntries={["/trips/trip/route/a2?fromActivityId=a1&returnTo=%2Ftrips%2Ftrip%3Fview%3Dexecution"]}><Routes><Route path="/trips/:tripId/route/:activityId" element={<JourneyRoutePage repository={repo as never} />} /></Routes></MemoryRouter>);
}
beforeEach(() => { sessionStorage.clear(); vi.clearAllMocks(); });
afterEach(() => vi.unstubAllGlobals());
describe("formal activity route", () => {
  it("queries coordinates without using formal candidate IDs and restores returned route", async () => {
    const fetcher = vi.fn(async () => ({ ok: true, json: async () => ({ distance_meters: 1300, duration_seconds: 1100,
      path: [{ longitude: 120.1, latitude: 30.2, coordinate_system: "GCJ02" }], source: { provider: "amap", fetched_at: "now" } }) }));
    vi.stubGlobal("fetch", fetcher);
    const mounted = page();
    await screen.findByRole("heading", { name: "前往 正式目的地" });
    expect(screen.getByRole("link", { name: "← 返回旅行安排" }).getAttribute("href")).toBe("/trips/trip?view=execution");
    fireEvent.click(screen.getByRole("button", { name: "查询路线" }));
    await screen.findByText("1.3 公里 · 约 19 分钟");
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, options] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/routes/query");
    expect(JSON.parse(options.body as string)).toEqual({ mode: "walk", origin: { longitude: 120.1, latitude: 30.2, coordinate_system: "GCJ02" }, destination: { longitude: 120.1, latitude: 30.2, coordinate_system: "GCJ02" } });
    await waitFor(() => expect(sessionStorage.getItem("roamsync:journey-route:v1:trip:a2")).toContain("1300"));
    mounted.unmount(); page();
    await screen.findByText("1.3 公里 · 约 19 分钟");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("refuses unverified coordinate source and external return links", () => {
    expect(activityPoint({ ...destination, source: { ...destination.source, provider: "unknown" } })).toBeNull();
    expect(safeReturnTo("//evil.test", "trip")).toBe("/trips/trip");
    expect(safeReturnTo("/\\evil.test", "trip")).toBe("/trips/trip");
    expect(safeReturnTo("https://evil.test", "trip")).toBe("/trips/trip");
  });
  it("shows missing-coordinate state without route query", async () => {
    const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
    page({ ...repository, getDays: vi.fn(async () => [{ id: "day", activities: [{ ...destination, source: { provider: "unknown" } }] }]) } as never);
    await screen.findByText(/缺少可确认来源的地图坐标/);
    expect(fetcher).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "查询路线" })).toBeNull();
  });
  it("discards a late route after a map selection changes its origin", async () => {
    let finish!: (value: unknown) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise(resolve => { finish = resolve; })));
    page();
    await screen.findByRole("heading", { name: "前往 正式目的地" });
    fireEvent.click(screen.getByRole("button", { name: "查询路线" }));
    fireEvent.click(screen.getByRole("button", { name: "地图点选起点" }));
    finish({ ok: true, json: async () => ({ distance_meters: 1300, duration_seconds: 1100, path: [], source: { provider: "amap", fetched_at: "now" } }) });
    await waitFor(() => expect(screen.getByText("起点：地图所选位置")).toBeTruthy());
    expect(screen.queryByText("1.3 公里 · 约 19 分钟")).toBeNull();
    expect(screen.queryByRole("link", { name: "用高德地图出发 ↗" })).toBeNull();
  });
});
