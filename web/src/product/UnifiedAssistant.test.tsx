import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";
import { AssistantPage, TravelAssistantProvider, useTravelAssistant } from "./TravelAssistant";
import { arrangementAction, type Arrangement } from "./arrangementApi";
const trip = (id: string, version = 4): Arrangement => ({ version, trip: { id, title: id + "旅行", destination: "南京市", start_date: "2026-11-07", end_date: "2026-11-08", version }, days: [], items: [] });
const session = (id: string | null = null) => ({ id: id ? "session-" + id : "session", trip_id: id, latest_run_id: null, messages: [], pending_action: null });
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
function Controls() {
  const a = useTravelAssistant();
  return <><Link to="/trips/A">A</Link><Link to="/trips/B">B</Link><Link to="/">首页</Link><button onClick={() => a.openAssistant({ tripId: "A" })}>打开A</button><button onClick={() => a.openAssistant()}>打开当前助手</button><button onClick={a.resetContext}>自由聊</button><output>{a.arrangement?.trip.id}</output><span data-testid="arrangement-date">{a.arrangement?.trip.start_date}</span></>;
}
function mount(path = "/") {
  return render(<MemoryRouter initialEntries={[path]}><TravelAssistantProvider><Controls /><Routes><Route path="/" element={<AssistantPage />} /><Route path="*" element={<p>查看安排</p>} /></Routes></TravelAssistantProvider></MemoryRouter>);
}
beforeEach(() => { sessionStorage.clear(); localStorage.clear(); vi.stubEnv("VITE_DISCOVERY_PRODUCT", "true"); vi.stubEnv("VITE_ASSISTANT_CONTEXT_CONTRACT", "assistant-context-v1"); });
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
it("adopts into the same Provider session and the drawer continues that conversation with a version fence", async () => {
  localStorage.setItem("roamsync.discovery.topic", "unified-test");
  const requests: Array<{ url: string; body: Record<string, unknown> }> = [];
  let adopted = false;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const body = JSON.parse(String(init?.body || "{}")); requests.push({ url, body });
    if (url.endsWith("/assistant/sessions")) return response({ ...session(), pending_action: { id: "preview", title: "南京两日", summary: "留白建议", flexible: true, start_date: "2026-11-07", end_date: "2026-11-08", choices: [] } });
    if (url.endsWith("/decision")) { adopted = true; return response({ ...session("A"), id: "session", messages: [{ id: "m", user: "原始问题", assistant: "已经保存", context: { topic_id: localStorage.getItem("roamsync.discovery.topic") } }] }); }
    if (url.endsWith("/arrangement-items")) return response(trip("A", 7));
    if (url.endsWith("/messages/stream")) return new Response(`data: ${JSON.stringify({ type: "done", session: { ...session("A"), id: "session", messages: [] } })}\n\n`, { headers: { "Content-Type": "text/event-stream" } });
    throw Error("Unexpected " + url);
  }));
  mount(); fireEvent.click(await screen.findByRole("button", { name: "采用并保存这份安排" }));
  await waitFor(() => expect(screen.getByText("已经保存")).toBeVisible()); expect(adopted).toBe(true);
  fireEvent.click(screen.getByText("A")); fireEvent.click(screen.getByText("打开当前助手"));
  await screen.findByRole("dialog"); expect(screen.getByText("已经保存")).toBeVisible();
  fireEvent.change(screen.getByRole("textbox", { name: "告诉助手你的旅行想法" }), { target: { value: "玄武湖还是备选，不要排进去" } });
  fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
  await waitFor(() => expect(requests.some(r => r.url.endsWith("/messages/stream"))).toBe(true));
  const context = requests.find(r => r.url.endsWith("/messages/stream"))!.body.context as Record<string, unknown>;
  expect(context.action_target).toMatchObject({ trip_id: "A", expected_version: 7, operation: "edit_arrangement" });
  expect(requests.filter(r => r.url.endsWith("/assistant/sessions"))).toHaveLength(1);
});
it("refreshes the same Trip after adopting a date-change preview and uses its new version", async () => {
  let accepted = false;
  let actionTarget: unknown;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/assistant/sessions")) return response({ ...session("A"), pending_action: { id: "date-preview", title: "南京改期", summary: "改到下周", start_date: "2026-11-14", end_date: "2026-11-15" } });
    if (url.endsWith("/decision")) { accepted = true; return response(session("A")); }
    if (url.endsWith("/arrangement-items")) {
      const arrangement = trip("A", accepted ? 5 : 4);
      if (accepted) arrangement.trip.start_date = "2026-11-14";
      return response(arrangement);
    }
    if (url.endsWith("/messages/stream")) {
      actionTarget = JSON.parse(String(init?.body)).context.action_target;
      return new Response(`data: ${JSON.stringify({ type: "done", session: session("A") })}\n\n`, { headers: { "Content-Type": "text/event-stream" } });
    }
    throw Error(url);
  }));
  mount("/trips/A");
  await waitFor(() => expect(screen.getByTestId("arrangement-date")).toHaveTextContent("2026-11-07"));
  fireEvent.click(screen.getByText("打开当前助手"));
  fireEvent.click(await screen.findByRole("button", { name: "采用并保存这份安排" }));
  await waitFor(() => expect(screen.getByTestId("arrangement-date")).toHaveTextContent("2026-11-14"));
  fireEvent.change(screen.getByRole("textbox", { name: "告诉助手你的旅行想法" }), { target: { value: "玄武湖还是备选，不要排进去" } });
  fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
  await waitFor(() => expect(actionTarget).toMatchObject({ trip_id: "A", expected_version: 5, operation: "edit_arrangement" }));
});
it("drops a late arrangement read after switching Trips", async () => {
  let finishA!: (value: Response) => void;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/assistant/sessions")) return response(session(JSON.parse(String(init?.body)).trip_id));
    if (url.includes("/trips/A/")) return new Promise<Response>(resolve => { finishA = resolve; });
    if (url.includes("/trips/B/")) return response(trip("B"));
    throw Error(url);
  }));
  mount("/trips/A"); await waitFor(() => expect(finishA).toBeDefined());
  fireEvent.click(screen.getByText("B")); await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("B"));
  await act(async () => finishA(response(trip("A"))));
  expect(screen.getByRole("status")).toHaveTextContent("B");
});
it("explicit free chat on a Trip page stays unbound", async () => {
  const bodies: { trip_id: string | null }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/assistant/sessions")) { const body = JSON.parse(String(init?.body)); bodies.push(body); return response(session(body.trip_id)); }
    return response(trip("A"));
  }));
  mount("/trips/A"); await waitFor(() => expect(bodies.some(b => b.trip_id === "A")).toBe(true));
  fireEvent.click(screen.getByText("自由聊")); await waitFor(() => expect(bodies.at(-1)?.trip_id).toBeNull());
  fireEvent.click(screen.getByText("打开当前助手"));
  expect(screen.queryByText("已关联行程")).toBeNull();
});
it("completion in an old scope cannot cancel the new Trip read", async () => {
  let finishSend!: (value: Response) => void;
  let finishB!: (value: Response) => void;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/assistant/sessions")) return response(session(JSON.parse(String(init?.body)).trip_id));
    if (url.endsWith("/messages/stream")) return new Promise<Response>(resolve => { finishSend = resolve; });
    if (url.includes("/trips/B/")) return new Promise<Response>(resolve => { finishB = resolve; });
    if (url.includes("/trips/A/")) return response(trip("A"));
    throw Error(url);
  }));
  mount("/trips/A"); fireEvent.click(screen.getByText("打开A"));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("A"));
  fireEvent.change(screen.getByRole("textbox", { name: "告诉助手你的旅行想法" }), { target: { value: "保留玄武湖" } });
  fireEvent.click(screen.getByRole("button", { name: "发送消息" }));
  await waitFor(() => expect(finishSend).toBeDefined());
  fireEvent.click(screen.getByText("B")); await waitFor(() => expect(finishB).toBeDefined());
  await act(async () => finishSend(new Response(`data: ${JSON.stringify({ type: "done", session: session("A") })}\n\n`, { headers: { "Content-Type": "text/event-stream" } })));
  await act(async () => finishB(response(trip("B"))));
  expect(screen.getByRole("status")).toHaveTextContent("B");
});
it("declares existing date-change authority without weakening normal edits", () => {
  expect(arrangementAction("把出发日期改到2026-11-09", trip("A"), "m").operation).toBe("reschedule_trip");
  expect(arrangementAction("请调整第二天的安排", trip("A"), "m").operation).toBe("plan_trip");
});
