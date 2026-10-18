import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import type { ExplorePlace, ExploreRepository } from "../domain/explore";
import type { AssistantSession } from "../domain/types";
import { AssistantPage, TravelAssistantProvider, useTravelAssistant } from "./TravelAssistant";

const place: ExplorePlace = { id: "amap:B001", provider: "amap", provider_place_id: "B001", name: "西湖", city: "杭州市", address: "西湖区龙井路", category: "sight", location: { longitude: 120.1, latitude: 30.2, coordinate_system: "gcj02" }, rating: null, reference_cost_yuan: null, price_status: "unknown", photos: [], source_url: "https://amap.com", retrieved_at: "2026-10-15T00:00:00Z", description: null, phone: null };
const session = (tripId?: string): AssistantSession => ({ id: tripId ? "trip-session" : "global-session", trip_id: tripId ?? null, messages: [], latest_run_id: null, pending_action: null });
const explore = () => ({ search: vi.fn().mockResolvedValue({ items: [place], source: "amap", fetched_at: "today" }), detail: vi.fn(), favorites: vi.fn(), favorite: vi.fn(), route: vi.fn() } satisfies ExploreRepository);

function Controls() {
  const { openAssistant } = useTravelAssistant();
  return <><button onClick={() => openAssistant()}>打开助手</button><button onClick={() => openAssistant({ tripId: "trip-1" })}>聊行程</button><button onClick={() => openAssistant({ place })}>聊地点</button><Link to="/elsewhere">切换页面</Link></>;
}
function setup(initial = "/assistant", repository = { getAssistantSession: vi.fn(async (tripId?: string) => session(tripId)) }, exploreRepository = explore()) {
  render(<MemoryRouter initialEntries={[initial]}><TravelAssistantProvider tripRepository={repository} exploreRepository={exploreRepository}><Controls /><Routes><Route path="/assistant" element={<AssistantPage />} /><Route path="*" element={<div>另一个页面</div>} /></Routes></TravelAssistantProvider></MemoryRouter>);
  return { repository, exploreRepository };
}
function doneResponse(next: AssistantSession) {
  return new Response(`data: ${JSON.stringify({ type: "done", session: next })}\n\n`, { headers: { "Content-Type": "text/event-stream" } });
}
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); sessionStorage.clear(); localStorage.clear(); });

it("does not project legacy or other Topic messages into C's active Topic", async () => {
  vi.stubEnv("VITE_ASSISTANT_CONTEXT_CONTRACT", "assistant-context-v1");
  const next: AssistantSession = { ...session(), messages: [
    { id: "old", user: "旧会话问题", assistant: "旧会话回答" },
    { id: "other", user: "其他话题问题", assistant: "其他话题回答", context: { version: "assistant-context-v1", topic_id: "other" } },
    { id: "current", user: "当前话题问题", assistant: "当前话题回答", context: { version: "assistant-context-v1", topic_id: "travel-main" } },
  ] };
  setup("/assistant", { getAssistantSession: vi.fn().mockResolvedValue(next) });
  expect(await screen.findByText("当前话题回答")).toBeVisible();
  expect(screen.queryByText("旧会话回答")).not.toBeInTheDocument();
  expect(screen.queryByText("其他话题回答")).not.toBeInTheDocument();
});

it("opens C's server-matched canonical place cards without inventing provider IDs", async () => {
  const next: AssistantSession = { ...session(), messages: [{ id: "c-reply", user: "推荐一个地方", assistant: "可以看看这里。", place_cards: [{
    place: { place_id: "53283e50-7288-4727-a05c-9515e8268ea2", name: "服务端匹配地点", city: "杭州市", source: "amap", retrieved_at: "2026-10-15T00:00:00Z" },
    role: "recommendation", suggestion_ids: [], detail_path: "/places/53283e50-7288-4727-a05c-9515e8268ea2", reason_kind: "assistant_advice_unverified",
  }] }] };
  setup("/elsewhere", { getAssistantSession: vi.fn().mockResolvedValue(next) });
  await userEvent.click(screen.getByText("打开助手"));
  const link = await screen.findByRole("link", { name: "服务端匹配地点 · 杭州市" });
  expect(link).toHaveAttribute("href", "/places/53283e50-7288-4727-a05c-9515e8268ea2");
  await userEvent.click(link);
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

it("keeps the active global session and draft when navigating and reopening the drawer", async () => {
  const { repository } = setup();
  await waitFor(() => expect(screen.getByRole("button", { name: "发送消息" })).toBeDisabled());
  await waitFor(() => expect(repository.getAssistantSession).toHaveBeenCalledWith(undefined));
  await userEvent.type(screen.getByRole("textbox", { name: "告诉助手你的旅行想法" }), "苏州适合周末吗");
  await userEvent.click(screen.getByText("切换页面"));
  await userEvent.click(screen.getByText("打开助手"));
  expect(screen.getByRole("textbox", { name: "告诉助手你的旅行想法" })).toHaveValue("苏州适合周末吗");
  expect(repository.getAssistantSession).toHaveBeenCalledTimes(1);
});

it("uses explicit Trip scope and clears it when opening from a real place", async () => {
  const { repository } = setup("/elsewhere");
  await userEvent.click(screen.getByText("聊行程"));
  await waitFor(() => expect(repository.getAssistantSession).toHaveBeenCalledWith("trip-1"));
  expect(screen.getByRole("link", { name: "查看已确认安排" })).toHaveAttribute("href", "/trips/trip-1");
  await userEvent.click(screen.getByRole("button", { name: "关闭助手" }));
  await userEvent.click(screen.getByText("聊地点"));
  await waitFor(() => expect(repository.getAssistantSession).toHaveBeenLastCalledWith(undefined));
  expect(screen.queryByText("已关联行程")).not.toBeInTheDocument();
  expect(screen.getByText("西湖区龙井路 · 浏览的地点")).toBeVisible();
  expect(screen.getByRole("link", { name: "西湖" })).toHaveAttribute("href", "/places/amap%3AB001");
});

it("streams the independent Companion endpoint with actual browse context and no Trip or physical location", async () => {
  setup("/elsewhere");
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const fetchMock = vi.fn().mockResolvedValue(new Response(new ReadableStream<Uint8Array>({ start(value) { controller = value; } }), { headers: { "Content-Type": "text/event-stream" } }));
  vi.stubGlobal("fetch", fetchMock);
  await userEvent.click(screen.getByText("聊地点"));
  const input = screen.getByRole("textbox", { name: "告诉助手你的旅行想法" });
  await waitFor(() => expect(screen.getByRole("button", { name: "发送消息" })).toBeEnabled());
  fireEvent.change(input, { target: { value: "这里适合散步吗" } });
  await userEvent.click(screen.getByRole("button", { name: "发送消息" }));
  const [url, request] = fetchMock.mock.calls[0];
  expect(url).toBe("/api/v1/assistant/sessions/global-session/messages/stream");
  expect(JSON.parse(request.body)).toEqual({ message: "这里适合散步吗", message_id: expect.any(String), read_context: { surface: "explore", place: { id: place.id, name: place.name, city: place.city, address: place.address } } });
  act(() => controller.enqueue(new TextEncoder().encode('data: {"type":"answer_delta","delta":"湖边适合慢慢走。"}\n\n')));
  expect(await screen.findByText("湖边适合慢慢走。")).toBeVisible();
  const next = { ...session(), messages: [{ id: "reply", user: "这里适合散步吗", assistant: "湖边适合慢慢走。" }] };
  act(() => controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify({ type: "done", session: next })}\n\n`)));
  await waitFor(() => expect(screen.getByRole("button", { name: "发送消息" })).toBeDisabled());
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

it("only links search results with real provider identities and requires an explicit search city", async () => {
  const { exploreRepository } = setup("/assistant", { getAssistantSession: vi.fn().mockResolvedValue({ ...session(), messages: [{ id: "search-topic", user: "找个地方去", assistant: "可以搜索你感兴趣的地点。" }] }) });
  await userEvent.click(await screen.findByText("查看相关地点"));
  expect(screen.getByRole("button", { name: "查找地点" })).toBeDisabled();
  await userEvent.type(screen.getByRole("textbox", { name: "目的地城市" }), "杭州");
  await userEvent.clear(screen.getByRole("textbox", { name: "地点关键词" }));
  await userEvent.type(screen.getByRole("textbox", { name: "地点关键词" }), "西湖");
  await userEvent.click(screen.getByRole("button", { name: "查找地点" }));
  expect(exploreRepository.search).toHaveBeenCalledWith({ city: "杭州", q: "西湖", category: "all" });
  expect(await screen.findByRole("link", { name: "西湖" })).toHaveAttribute("href", "/places/amap%3AB001");
});

it("keeps exploration and favorites available after a model error and retries with the same message id", async () => {
  setup();
  const fetchMock = vi.fn().mockRejectedValueOnce(new Error("AI 服务暂不可用")).mockResolvedValueOnce(doneResponse({ ...session(), messages: [{ id: "m", user: "去哪里玩", assistant: "可以先比较喜欢的城市。" }] }));
  vi.stubGlobal("fetch", fetchMock);
  const input = screen.getByRole("textbox", { name: "告诉助手你的旅行想法" });
  await userEvent.type(input, "去哪里玩");
  await waitFor(() => expect(screen.getByRole("button", { name: "发送消息" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "发送消息" }));
  expect(await screen.findByText("AI 服务暂不可用")).toBeVisible();
  expect(screen.getByRole("link", { name: "继续探索" })).toHaveAttribute("href", "/explore");
  expect(screen.getByRole("link", { name: "我的收藏" })).toHaveAttribute("href", "/favorites");
  expect(input).toHaveValue("去哪里玩");
  await userEvent.click(screen.getByRole("button", { name: "发送消息" }));
  expect(await screen.findByText("可以先比较喜欢的城市。")).toBeVisible();
  expect(JSON.parse(fetchMock.mock.calls[0][1].body).message_id).toBe(JSON.parse(fetchMock.mock.calls[1][1].body).message_id);
});

it("renders a grounded AI route and carries canonical endpoints to the map", async () => {
  vi.stubEnv("VITE_ASSISTANT_CONTEXT_CONTRACT", "assistant-context-v1");
  const next: AssistantSession = { ...session(), messages: [{ id: "route-reply", user: "查询步行路线", assistant: "路线结果如下。",
    context: { version: "assistant-context-v1", topic_id: "travel-main", route_request: { origin_place_id: "7489846f-f1da-596d-97f9-1a4c0a30164d", destination_place_id: "b0f84042-d619-5de6-999a-fb6e7541fa7e", mode: "walk" } },
    read_tools: { route: { status: "available", result: { mode: "walk", distance_meters: 1234, duration_seconds: 900 } } },
  }] };
  setup("/assistant", { getAssistantSession: vi.fn().mockResolvedValue(next) });
  expect(await screen.findByText("1.2 公里 · 预计 15 分钟")).toBeVisible();
  expect(screen.getByRole("link", { name: "打开路线地图" })).toHaveAttribute("href", "/places/b0f84042-d619-5de6-999a-fb6e7541fa7e/route?origin_place_id=7489846f-f1da-596d-97f9-1a4c0a30164d&mode=walk");
});

it("shows unavailable AI routes without inventing an estimated result", async () => {
  const next: AssistantSession = { ...session(), messages: [{ id: "route-failure", user: "查询路线", assistant: "请稍后再试。", read_tools: { route: { status: "unavailable" } } }] };
  setup("/assistant", { getAssistantSession: vi.fn().mockResolvedValue(next) });
  expect(await screen.findByText("路线暂不可用，请稍后重试或在地点详情中查询路线。")).toBeVisible();
  expect(screen.queryByRole("link", { name: "打开路线地图" })).not.toBeInTheDocument();
});
