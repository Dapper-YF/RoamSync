import { render, screen, waitFor, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NaturalAssistant } from "./NaturalAssistant";

const item = { id: "choice", kind: "selected", label: "玄武湖", place_id: null, source_ref: "user-original", decision_ref: "user-original", activity_id: null, day_date: null, start: null, end: null };
const base = { version: 7, trip: { id: "trip", title: "南京两日", destination: "南京市", start_date: "2026-11-07", end_date: "2026-11-08" }, days: [{ id: "day", date: "2026-11-07", activities: [], route_legs: [] }], items: [item] };
const session = { id: "session", trip_id: "trip", messages: [], pending_action: null, latest_run_id: null };
const mount = (path = "/arrangements/trip") => render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/arrangements/:tripId" element={<NaturalAssistant />} /><Route path="/" element={<NaturalAssistant />} /></Routes></MemoryRouter>);
beforeEach(() => { localStorage.clear(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("natural assistant result boundary", () => {
  it("persists a page decision with the displayed version and reloads the common result", async () => {
    let current = base;
    const requests: { url: string; init?: RequestInit }[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      requests.push({ url, init });
      if (url.endsWith("/assistant/sessions")) return new Response(JSON.stringify(session));
      if (init?.method === "PUT") { current = { ...base, version: 8, items: [{ ...item, kind: "optional" }] }; return new Response(JSON.stringify(current.items[0])); }
      return new Response(JSON.stringify(current));
    }));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "改为备选" }));
    await screen.findByText("备选 · 可以不去");
    const edit = requests.find(r => r.init?.method === "PUT");
    expect(JSON.parse(edit!.init!.body as string)).toMatchObject({ expected_version: 7, kind: "optional", place_id: null });
    expect(requests.filter(r => r.url.includes("planning-runs"))).toHaveLength(0);
    expect(await screen.findByText("已保存这项决定，其他时间没有重新安排。")).toBeInTheDocument();
  });

  it("shows a human conflict and never retries the stale edit automatically", async () => {
    const update = vi.fn();
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/assistant/sessions")) return new Response(JSON.stringify(session));
      if (init?.method === "PUT") { update(); return new Response(JSON.stringify({ detail: { code: "trip_version_conflict" } }), { status: 409 }); }
      return new Response(JSON.stringify(base));
    }));
    mount();
    fireEvent.click(await screen.findByRole("button", { name: "改为备选" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("本次操作没有覆盖它");
    expect(update).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("trip_version_conflict")).not.toBeInTheDocument();
  });

  it("sends chat changes against the same displayed Trip and message identity", async () => {
    const messages: Record<string, unknown>[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/assistant/sessions")) return new Response(JSON.stringify(session));
      if (url.endsWith("/messages")) { messages.push(JSON.parse(init!.body as string)); return new Response(JSON.stringify(session)); }
      return new Response(JSON.stringify(base));
    }));
    mount();
    await screen.findByText("玄武湖");
    fireEvent.change(screen.getByLabelText("告诉助手你的问题或变化"), { target: { value: "把玄武湖改成备选" } });
    await waitFor(() => expect(screen.getByRole("button", { name: "发送" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(messages).toHaveLength(1));
    const body = messages[0] as { message_id: string; context: { action_target: object } };
    expect(body.context.action_target).toMatchObject({ trip_id: "trip", expected_version: 7, operation: "edit_arrangement", authorization_message_id: body.message_id });
  });

  it("opens a free conversation without creating a Trip or a plan", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => { urls.push(url); return new Response(JSON.stringify({ ...session, trip_id: null })); }));
    mount("/");
    await screen.findByText("先聊聊，也很好");
    await waitFor(() => expect(urls).toContain("/api/v1/assistant/sessions"));
    expect(urls.some(url => /\/trips|planning-runs/.test(url))).toBe(false);
  });
});
