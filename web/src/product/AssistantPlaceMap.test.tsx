import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { AssistantPlaceMap } from "./AssistantPlaceMap";
vi.mock("./ExploreMap", () => ({ ExploreMap: ({ ariaLabel }: { ariaLabel: string }) => <div role="region" aria-label={ariaLabel}>真实地点地图组件</div> }));
const card = { place: { place_id: "ff426743-165e-5ddf-b61f-eb2b81eb4bba", name: "玄武湖景区", city: "南京市", source: "https://www.amap.com", retrieved_at: "2026-10-20", longitude: 118.8, latitude: 32.06, coordinate_system: "gcj02" }, role: "recommendation" as const, suggestion_ids: [], detail_path: "/places/ff426743-165e-5ddf-b61f-eb2b81eb4bba", reason_kind: "retrieved_reference" as const };
it("shows the existing map without an extra action and keeps the detail destination", () => {
  render(<MemoryRouter><AssistantPlaceMap cards={[card]} /></MemoryRouter>);
  expect(screen.getByRole("region", { name: "回答中的地点地图" })).toBeVisible();
  expect(screen.getByRole("link", { name: "查看玄武湖景区详情" })).toHaveAttribute("href", card.detail_path);
  expect(screen.queryByText(/高德评分|00:00/)).toBeNull();
});
it("keeps details when old messages lack usable coordinates, without inventing a map location", () => {
  render(<MemoryRouter><AssistantPlaceMap cards={[{ ...card, place: { ...card.place, longitude: null } }]} /></MemoryRouter>);
  expect(screen.queryByRole("region", { name: "回答中的地点地图" })).toBeNull();
  expect(screen.getByRole("link", { name: "查看玄武湖景区详情" })).toBeVisible();
});
