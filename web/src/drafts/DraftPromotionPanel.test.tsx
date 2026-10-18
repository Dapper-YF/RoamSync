import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { DraftPromotionPanel } from "./DraftPromotionPanel";
import type { Draft } from "../data/draftRepository";

const draft: Draft = { id: "draft-1", city: "杭州", title: "杭州一天", day_count: 1, requirements: "", version: 2,
  status: "active", saved: true, plan: { days: [] }, runs: [], updated_at: "2026-10-15T10:00:00Z" };
const plan = { id: "prepared-1", draft_id: draft.id, draft_version: 2, operation_id: null, city: "杭州", prepared_hash: "a".repeat(64),
  constraints: { start_date: "2026-11-01", total_budget_fen: null, daily_budget_fen: null, transport_mode: "driving" }, end_date: "2026-11-01",
  expires_at: "2099-01-01T00:00:00Z", activities: [{ ref: "a", day_date: "2026-11-01", position: 0, name: "真实地点", place_id: "real-id",
    planned_start_time: "09:00:00", duration_minutes: 90, transport_mode: "driving", estimated_cost_fen: 10000, cost_nature: "planning_estimate", note: "建议" }],
  routes: [], coverage: { checked: ["真实地点已核实"], missing: ["营业时间未核实"], blockers: [] } };
const op = { id: "operation-1", draft_id: draft.id, status: "requested", target_trip_id: null, error: null };
const json = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); });

it("prepares without creating and confirms exactly the displayed hash with an explicit action", async () => {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/promotion-preview")) return json(plan);
    if (url.endsWith("/draft-promotions")) return json(op);
    if (url.endsWith("/resume")) return json({ ...op, status: "applied", target_trip_id: "trip-1" });
    return json([]);
  });
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter><DraftPromotionPanel draft={draft} /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("出发日期"), { target: { value: "2026-11-01" } });
  fireEvent.click(screen.getByRole("button", { name: "准备日期和完整方案" }));
  const preview = await screen.findByRole("article", { name: "待确认的完整方案" });
  expect(within(preview).getByText(/规划估算/)).toHaveTextContent("¥100.00");
  expect(within(preview).getByText("营业时间未核实")).toBeInTheDocument();
  expect(fetcher.mock.calls.some(([url]) => url.endsWith("/draft-promotions"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "创建并采用当前方案" }));
  await screen.findByText("旅行已创建，当前方案已采用");
  expect(screen.getByRole("link", { name: "查看已创建的旅行" })).toHaveAttribute("href", "/trips/trip-1");
  const submitted = fetcher.mock.calls.find(([url]) => url.endsWith("/draft-promotions"));
  expect(JSON.parse(String(submitted?.[1]?.body))).toMatchObject({ prepared_id: "prepared-1", prepared_hash: plan.prepared_hash,
    action: "create_and_adopt", confirmation: "创建并采用当前方案" });
});

it("keeps unresolved places visible, blocks adoption, and permits explicit create-only", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => url.endsWith("/promotion-preview") ? json({ ...plan,
    activities: [{ ...plan.activities[0], name: "未明确地点", place_id: null }], coverage: { ...plan.coverage, blockers: ["请在草稿中选择真实地点"] } }) : json([])));
  render(<MemoryRouter><DraftPromotionPanel draft={draft} /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("出发日期"), { target: { value: "2026-11-01" } });
  fireEvent.click(screen.getByRole("button", { name: "准备日期和完整方案" }));
  await screen.findByText("请在草稿中选择真实地点");
  expect(screen.getByText(/未明确地点/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "创建并采用当前方案" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "只创建旅行，暂不采用方案" })).toBeEnabled();
});

it("restores failed-operation Trip links and resumes the same operation after refresh", async () => {
  const fetcher = vi.fn(async (url: string) => json(url.endsWith("/resume") ? { ...op, status: "applied", target_trip_id: "trip-kept" } :
    [{ ...op, status: "failed", target_trip_id: "trip-kept", error: "旅行已创建，处理可恢复" }]));
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter><DraftPromotionPanel draft={draft} /></MemoryRouter>);
  await screen.findByText("旅行已创建，处理可恢复");
  expect(screen.getByRole("link", { name: "查看已创建的旅行" })).toHaveAttribute("href", "/trips/trip-kept");
  fireEvent.click(screen.getByRole("button", { name: "恢复当前操作" }));
  await screen.findByText("旅行已创建，当前方案已采用");
  expect(fetcher.mock.calls.some(([url]) => url.endsWith("/draft-promotions/operation-1/resume"))).toBe(true);
});

it("retains typed calendar text across transport changes and rejects invalid calendar dates", async () => {
  const fetcher = vi.fn(async (url: string) => json(url.endsWith("/promotion-preview") ? plan : []));
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter><DraftPromotionPanel draft={draft} /></MemoryRouter>);
  const date = screen.getByLabelText("出发日期");
  fireEvent.input(date, { target: { value: "2026-11-01" } });
  fireEvent.change(screen.getByLabelText("交通方式"), { target: { value: "driving" } });
  expect(date).toHaveValue("2026-11-01");
  fireEvent.click(screen.getByRole("button", { name: "准备日期和完整方案" }));
  await screen.findByRole("article", { name: "待确认的完整方案" });
  const request = fetcher.mock.calls.find(([url]) => url.endsWith("/promotion-preview"));
  expect(request).toBeDefined();
  fireEvent.input(date, { target: { value: "2026-02-30" } });
  fireEvent.click(screen.getByRole("button", { name: "准备日期和完整方案" }));
  await screen.findByText("请按YYYY-MM-DD填写有效的出发日期，例如2026-11-01。");
  expect(fetcher.mock.calls.filter(([url]) => url.endsWith("/promotion-preview"))).toHaveLength(1);
});
