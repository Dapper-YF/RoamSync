import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { DraftPages } from "./DraftPages";
import type { Draft } from "../data/draftRepository";

const draft: Draft = { id: "123", city: "杭州", title: "杭州三日", day_count: 3, requirements: "", version: 1,
  status: "active", saved: false, plan: null, runs: [], updated_at: "2026-10-15T10:00:00Z" };
const json = (value: unknown) => new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("creates an undated draft and opens its editor without a Trip request", async () => {
  const fetcher = vi.fn(async (_url: string, init?: RequestInit) => json(init?.method === "POST" ? draft : _url.endsWith("/123") ? draft : []));
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter initialEntries={["/drafts"]}><Routes><Route path="/drafts/*" element={<DraftPages />} /></Routes></MemoryRouter>);
  fireEvent.click(screen.getByRole("button", { name: "创建未定日期草稿" }));
  await screen.findByRole("heading", { name: "杭州三日" });
  expect(fetcher.mock.calls.every(([url]) => url.startsWith("/api/v1/drafts"))).toBe(true);
  const submission = fetcher.mock.calls.find(([, init]) => init?.method === "POST");
  expect(JSON.parse(String(submission?.[1]?.body))).toMatchObject({ city: "杭州", day_count: 3 });
  expect(String(submission?.[1]?.body)).not.toContain("start_date");
});

it("restores a cancelled draft and marks unknown locations", async () => {
  const cancelled = { ...draft, status: "cancelled", plan: { days: [{ day_index: 1, title: "散步", items: [{ name: "未确认公园", note: "散步建议", place_id: null, identity_status: "unknown" }] }] } };
  const fetcher = vi.fn(async (_url: string, init?: RequestInit) => json(init ? { ...cancelled, status: "active", version: 2 } : cancelled));
  vi.stubGlobal("fetch", fetcher);
  render(<MemoryRouter initialEntries={["/drafts/123"]}><Routes><Route path="/drafts/*" element={<DraftPages />} /></Routes></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "恢复草稿" }));
  await screen.findByRole("button", { name: "按要求修改草稿" });
  expect(screen.getByText("未确认公园 · 地点待确认")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "未确认公园" })).not.toBeInTheDocument();
});

it("shows a recoverable failure and keeps the existing plan", async () => {
  vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => init ? new Response(JSON.stringify({ detail: { message: "服务暂不可用" } }), { status: 503 }) : json({ ...draft,
    plan: { days: [{ day_index: 1, title: "原内容", items: [] }] } })));
  render(<MemoryRouter initialEntries={["/drafts/123"]}><Routes><Route path="/drafts/*" element={<DraftPages />} /></Routes></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "按要求修改草稿" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("服务暂不可用"));
  expect(screen.getByText("第1天 · 原内容")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "刷新重试" })).toBeInTheDocument();
});
