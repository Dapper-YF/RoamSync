import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ExplorePlace, ExploreRepository } from "../domain/explore";
import { ExplorePage, FavoritesPage, PlaceDetailPage, ProductLayout } from "./ProductExperience";

const assistant = vi.hoisted(() => ({ openAssistant: vi.fn() }));
vi.mock("./TravelAssistant", () => ({ useTravelAssistant: () => assistant }));

const place: ExplorePlace = {
  id: "amap:poi-1", provider: "amap", provider_place_id: "poi-1", name: "西湖边的茶馆", category: "food", city: "杭州市", address: "杭州市西湖区湖滨路",
  location: { longitude: 120.16, latitude: 30.25, coordinate_system: "gcj02" }, rating: null, reference_cost_yuan: null, price_status: "unknown", photos: [],
  source_url: "https://example.test/place/poi-1", retrieved_at: "2026-10-15T08:00:00Z", description: null, phone: null,
};

function repository(overrides: Partial<ExploreRepository> = {}): ExploreRepository {
  return {
    search: vi.fn().mockResolvedValue({ items: [place], fetched_at: "2026-10-15T08:00:00Z", source: "高德地图" }),
    detail: vi.fn().mockResolvedValue(place),
    favorites: vi.fn().mockResolvedValue({ items: [], fetched_at: "2026-10-15T08:00:00Z", source: "RoamSync" }),
    favorite: vi.fn().mockResolvedValue(undefined),
    route: vi.fn(),
    ...overrides,
  };
}

function cityLookup() {
  return vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), window.location.origin);
    const keyword = url.searchParams.get("keyword") ?? "";
    const name = keyword.startsWith("成") ? "成都市" : "杭州市";
    return { ok: true, json: async () => [{ name, adcode: name === "成都市" ? "510100" : "330100", citycode: "0571", longitude: 120.16, latitude: 30.25 }] };
  });
}

function mount(path: string, repo: ExploreRepository) {
  return render(<MemoryRouter initialEntries={[path]}><Routes><Route element={<ProductLayout repository={repo} />}>
    <Route path="/" element={<ExplorePage />} />
    <Route path="/places/:placeId" element={<PlaceDetailPage />} />
    <Route path="/favorites" element={<FavoritesPage />} />
  </Route></Routes></MemoryRouter>);
}

it("searches a selected real city and category through the explore repository", async () => {
  vi.stubGlobal("fetch", cityLookup());
  const repo = repository();
  mount("/", repo);
  await screen.findByText("西湖边的茶馆");

  fireEvent.change(screen.getByRole("textbox", { name: "目的地城市" }), { target: { value: "成都" } });
  fireEvent.click(await screen.findByRole("option", { name: /成都市/ }));
  fireEvent.change(screen.getByRole("textbox", { name: "地点关键词" }), { target: { value: "老茶馆" } });
  fireEvent.click(screen.getByRole("button", { name: "尝美食" }));

  await waitFor(() => expect(repo.search).toHaveBeenLastCalledWith({ city: "成都市", q: "老茶馆", category: "food" }, expect.any(AbortSignal)));
  vi.unstubAllGlobals();
});

it("starts from a representative city theme and scopes theme chips to their place category", async () => {
  vi.stubGlobal("fetch", cityLookup());
  const discover = vi.fn().mockResolvedValue({ items: [place], fetched_at: place.retrieved_at, source: "amap" });
  mount("/", repository({ discover }));

  await screen.findByText("西湖边的茶馆");
  await waitFor(() => expect(discover).toHaveBeenNthCalledWith(1,
    { city: "杭州市", q: "景点", category: "sight" },
    expect.objectContaining({ use_preferences: true }), expect.any(AbortSignal)));
  expect(screen.getByRole("textbox", { name: "地点关键词" })).toHaveValue("景点");
  expect(screen.getByRole("button", { name: "看风景" })).toHaveAttribute("aria-pressed", "true");

  fireEvent.click(screen.getByRole("button", { name: "茶馆" }));
  await waitFor(() => expect(discover).toHaveBeenLastCalledWith(
    { city: "杭州市", q: "茶馆", category: "food" }, expect.any(Object), expect.any(AbortSignal)));
  vi.unstubAllGlobals();
});

it("shows unknown facts honestly and saves a place through the API", async () => {
  let saved = false;
  const repo = repository({
    favorites: vi.fn().mockImplementation(async () => ({ items: saved ? [{ ...place, favorite: true }] : [], fetched_at: "2026-10-15T08:00:00Z", source: "RoamSync" })),
    favorite: vi.fn().mockImplementation(async (_id: string, value: boolean) => { saved = value; }),
  });
  const view = mount("/places/amap%3Apoi-1", repo);
  expect(await screen.findByRole("heading", { name: "西湖边的茶馆" })).toBeVisible();
  expect(screen.getByText("暂无评分")).toBeVisible();
  expect(screen.getByText("暂无参考价")).toBeVisible();
  expect(screen.getByText("暂无可用照片")).toBeVisible();
  expect(screen.getByText("暂时没有地点介绍。")).toBeVisible();

  fireEvent.click(screen.getByRole("button", { name: "收藏这个地点" }));
  await waitFor(() => expect(repo.favorite).toHaveBeenCalledWith(place.id, true));
  fireEvent.click(screen.getByRole("button", { name: "问问这里" }));
  expect(assistant.openAssistant).toHaveBeenCalledWith(expect.objectContaining({ place: expect.objectContaining({ id: place.id, favorite: true }), prompt: expect.stringContaining(place.name) }));
  view.unmount();

  mount("/places/amap%3Apoi-1", repo);
  expect(await screen.findByRole("button", { name: "已收藏" })).toBeVisible();
  expect(repo.favorites).toHaveBeenCalledTimes(2);
  vi.unstubAllGlobals();
});

it("loads the real favorites endpoint and offers exploration when it is empty", async () => {
  const repo = repository({ favorites: vi.fn().mockResolvedValue({ items: [], fetched_at: "2026-10-15T08:00:00Z", source: "RoamSync" }) });
  mount("/favorites", repo);
  expect(await screen.findByRole("heading", { name: "这里还空着" })).toBeVisible();
  expect(repo.favorites).toHaveBeenCalledWith(expect.any(AbortSignal));
  expect(screen.getByRole("link", { name: /去探索/ })).toHaveAttribute("href", "/");
});

it("applies only an explicitly confirmed nearby point and user filters", async () => {
  vi.stubGlobal("fetch", cityLookup());
  const discover = vi.fn().mockResolvedValue({ items: [{ ...place, recommendation_reasons: ["匹配显式偏好"] }], fetched_at: place.retrieved_at, source: "amap" });
  const repo = repository({ discover }); mount("/", repo);
  await screen.findByText("西湖边的茶馆");
  fireEvent.click(screen.getByRole("checkbox", { name: "搜索所选位置附近" }));
  fireEvent.change(screen.getByRole("textbox", { name: "附近经度" }), { target: { value: "120.16" } });
  fireEvent.change(screen.getByRole("textbox", { name: "附近纬度" }), { target: { value: "30.25" } });
  fireEvent.click(screen.getByRole("button", { name: "确认附近位置" }));
  fireEvent.change(screen.getByRole("combobox", { name: "最低评分" }), { target: { value: "4" } });
  fireEvent.click(screen.getByRole("button", { name: "应用筛选" }));
  await waitFor(() => expect(discover).toHaveBeenLastCalledWith(expect.objectContaining({ city: "杭州市" }), expect.objectContaining({ center: { longitude: 120.16, latitude: 30.25, coordinate_system: "gcj02" }, min_rating: 4 }), expect.any(AbortSignal)));
  expect(screen.getByText("匹配显式偏好")).toBeVisible(); vi.unstubAllGlobals();
});
