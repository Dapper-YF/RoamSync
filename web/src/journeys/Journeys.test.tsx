import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { JourneyDraftPage } from "./JourneyDraftPage";
import { JourneysPage } from "./JourneysPage";
import type { Draft } from "../data/draftRepository";
import { JourneyPromotion } from "./JourneyPromotion";

const draft: Draft = { id: "draft-1", city: "成都", title: "周末慢游", day_count: 2, requirements: "轻松", version: 1, status: "active", saved: true, plan: { days: [ { day_index: 1, title: "第一天", items: [{ name: "草稿活动", note: "原备注", place_id: null, identity_status: "unknown" }] }, { day_index: 2, title: "第二天", items: [{ name: "保留活动", note: "不变", place_id: null, identity_status: "unknown" }] } ] }, runs: [], updated_at: "2026-10-16" };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
const emptyRequirements = { version: 1, records: [], effective_by_day: { "1": [], "2": [] } };
afterEach(() => { cleanup(); sessionStorage.clear(); vi.unstubAllGlobals(); });
function editor() { return render(<MemoryRouter initialEntries={["/drafts/draft-1"]}><Routes><Route path="/drafts/:draftId" element={<JourneyDraftPage />} /></Routes></MemoryRouter>); }
it("keeps unsaved draft edits through leaving, refresh and version conflict without overwriting them", async () => {
  let current = structuredClone(draft);
  const fetcher = vi.fn(async (url: string, _init?: RequestInit) => json(url.endsWith("/requirements") ? emptyRequirements : url.endsWith("/promotions") ? [] : current));
  vi.stubGlobal("fetch", fetcher);
  const view = editor();
  fireEvent.change(await screen.findByLabelText("第1天第1站备注"), { target: { value: "尚未保存的想法" } });
  await waitFor(() => expect(sessionStorage.getItem("roamsync.journeys.draft.draft-1.edit")).toContain("尚未保存的想法"));
  view.unmount();
  current = { ...current, version: 2, title: "另一处已更新" };
  editor();
  expect(await screen.findByDisplayValue("尚未保存的想法")).toBeInTheDocument();
  expect(screen.getByText(/草稿已有更新/)).toBeInTheDocument();
  expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
});
it("saves only after reviewing a complete before/after and sends the protected version", async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => json(url.endsWith("/requirements") ? emptyRequirements : url.endsWith("/promotions") ? [] : init ? { ...draft, ...JSON.parse(String(init.body)), version: 2 } : draft));
  vi.stubGlobal("fetch", fetcher); editor();
  fireEvent.change(await screen.findByLabelText("第1天第1站备注"), { target: { value: "新的备注" } });
  fireEvent.click(screen.getByRole("button", { name: "核对并保存修改" }));
  expect(fetcher.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  expect(screen.getByText("第2天 · 保持原样")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "确认保存修改" }));
  await screen.findByText("修改已保存，离开后可以继续。");
  const call = fetcher.mock.calls.find(([url]) => url.endsWith("/edit"));
  const body = JSON.parse(String(call?.[1]?.body));
  expect(body.expected_version).toBe(1);
  expect(body.plan.days[1]).toEqual(draft.plan!.days[1]);
  expect(body.plan.days[0].items[0].note).toBe("新的备注");
});
it("sends a selected relative day as backend-enforced scope and creates no Trip", async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => json(url.endsWith("/requirements") ? emptyRequirements : url.endsWith("/promotions") ? [] : init ? { ...draft, version: 2 } : draft));
  vi.stubGlobal("fetch", fetcher); editor();
  fireEvent.change(await screen.findByLabelText("调整范围"), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("第2天怎样调整"), { target: { value: "第二天减少步行" } });
  fireEvent.click(screen.getByRole("button", { name: "按范围调整草稿" }));
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => url.endsWith("/runs"))).toBe(true));
  const body = JSON.parse(String(fetcher.mock.calls.find(([url]) => url.endsWith("/runs"))?.[1]?.body));
  expect(body.target_day_indices).toEqual([2]); expect(body.expected_version).toBe(1);
  expect(fetcher.mock.calls.every(([url]) => !url.includes("/trips"))).toBe(true);
});
it("starts a new draft without a preset city, location permission or formal Trip", async () => {
  const fetcher = vi.fn(async (url: string, _init?: RequestInit) => json(url.endsWith("/trips") || url.endsWith("/drafts") ? [] : draft));
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter initialEntries={["/drafts/new"]}><JourneysPage /></MemoryRouter>);
  expect(screen.getByLabelText("想去哪里")).toHaveValue("");
  await screen.findByRole("button", { name: "开始筹划" });
  expect(fetcher.mock.calls.every(([, init]) => !init?.method || init.method === "GET")).toBe(true);
});
it("reports a model failure returned in HTTP 200 without claiming generation is underway", async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/requirements")) return json(emptyRequirements);
    if (url.endsWith("/promotions")) return json([]);
    if (url.endsWith("/runs") && init) { const body = JSON.parse(String(init.body)); return json({ ...draft, version: 2, runs: [{ id: "failed-run", request_id: body.request_id, status: "failed", error: "模型服务未完成请求，原草稿仍保留", requirements: body.requirements, source: "model", created_at: "2026-10-16", finished_at: "2026-10-16" }] }); }
    return json(draft);
  });
  vi.stubGlobal("fetch", fetcher); editor();
  fireEvent.change(await screen.findByLabelText("这次希望怎样安排"), { target: { value: "安排轻松一些" } });
  fireEvent.click(screen.getByRole("button", { name: "按范围调整草稿" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("模型服务未完成请求，原草稿仍保留"));
  expect(screen.queryByText(/正在按你的要求整理/)).not.toBeInTheDocument();
  expect(screen.getByLabelText("第1天第1站备注")).toHaveValue("原备注");
  fireEvent.click(screen.getByRole("button", { name: "按范围调整草稿" }));
  await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url.endsWith("/runs"))).toHaveLength(2));
  const requests = fetcher.mock.calls.filter(([url]) => url.endsWith("/runs")).map(([, init]) => JSON.parse(String(init?.body)).request_id);
  expect(requests[1]).not.toBe(requests[0]);
});
it("locks a lost promotion response to the same authorization and request id", async () => {
  sessionStorage.setItem("roamsync.journeys.draft.draft-1.prepared", JSON.stringify({ id: "prepared-1", draft_id: draft.id, draft_version: 1, title: "待确认旅行", city: "成都", requirements: "", prepared_hash: "hash", expires_at: "2099-01-01", constraints: { start_date: "2026-11-01", transport_mode: "walk", total_budget_fen: null, daily_budget_fen: null }, end_date: "2026-11-02", activities: [], routes: [], coverage: { checked: [], missing: [], blockers: [] } }));
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => { if (init?.method === "POST") throw new Error("响应中断"); return json([]); });
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter><JourneyPromotion draft={draft} disabled={false} /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "确认创建并采用这份日程" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("响应中断"));
  expect(screen.getByRole("button", { name: "只创建旅行，日程稍后确认" })).toBeDisabled();
  expect(screen.getByLabelText("出发日期")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "确认创建并采用这份日程" }));
  await waitFor(() => expect(fetcher.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(2));
  const bodies = fetcher.mock.calls.filter(([, init]) => init?.method === "POST").map(([, init]) => JSON.parse(String(init?.body)));
  expect(bodies[0].request_id).toBe(bodies[1].request_id);
  expect(bodies.every(body => body.action === "create_and_adopt")).toBe(true);
});
it("polls an in-flight generation and allows cancellation before its HTTP request finishes", async () => {
  let current = structuredClone(draft);
  let finish: ((response: Response) => void) | undefined;
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/requirements")) return json(emptyRequirements);
    if (url.endsWith("/promotions")) return json([]);
    if (url.endsWith("/runs") && init) {
      const input = JSON.parse(String(init.body));
      current = { ...current, version: 2, runs: [{ id: "running-run", request_id: input.request_id, status: "running", requirements: input.requirements, source: "model", error: null, created_at: "2026-10-16", finished_at: null }] };
      return new Promise<Response>(resolve => { finish = resolve; });
    }
    if (url.endsWith("/cancel-run") && init) {
      current = { ...current, version: 3, runs: current.runs.map(run => ({ ...run, status: "cancelled" })) };
      finish?.(json(current)); return json(current);
    }
    return json(current);
  });
  vi.stubGlobal("fetch", fetcher); editor();
  fireEvent.change(await screen.findByLabelText("这次希望怎样安排"), { target: { value: "重新整理" } });
  fireEvent.click(screen.getByRole("button", { name: "按范围调整草稿" }));
  const stop = await screen.findByRole("button", { name: "停止本次整理" });
  await waitFor(() => expect(stop).toBeEnabled(), { timeout: 5000 });
  fireEvent.click(stop);
  await waitFor(() => expect(screen.getByRole("button", { name: "按范围调整草稿" })).toBeEnabled());
  expect(fetcher.mock.calls.some(([url]) => url.endsWith("/cancel-run"))).toBe(true);
  expect(screen.getByLabelText("第1天第1站备注")).toHaveValue("原备注");
}, 10000);


