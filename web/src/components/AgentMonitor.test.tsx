import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AgentMonitor, type MonitorClient, type MonitorRun, type MonitorTrace } from "./AgentMonitor";
import { MONITOR_CHANNEL, type DialogueObservation } from "../utils/agentMonitorChannel";

const run = (id = "real-run-a", status = "awaiting_confirmation"): MonitorRun => ({ id, trip_id: "trip-a", trip_title: "杭州测试旅行", status, intent: "modify_day", base_trip_version: 18, current_trip_version: 18, model: "test-model", provider: "test", created_at: "2026-09-29T10:00:00Z", started_at: "2026-09-29T10:00:01Z", completed_at: null, planning_finished_at: "2026-09-29T10:00:23Z" });
const trace = (id = "real-run-a", status = "awaiting_confirmation"): MonitorTrace => ({
  contract_version: 1, run: run(id, status), tools: [], events: [], limitations: [], observations_truncated: false, error: null,
  stages: [
    { id: "message", title: "User Message", status: "completed", started_at: null, completed_at: null, duration_ms: null, attempts: 0, source: "run", data: { message: `请求 ${id}` } },
    { id: "context", title: "Context Building", status: "completed", started_at: null, completed_at: null, duration_ms: 241, attempts: 1, source: "progress.events", data: { available_count: 1, items: [{ label: "Formal Itinerary", available: true, data: [{ name: "西湖" }] }, { label: "Navigation ETA", available: false, data: null }] } },
    { id: "research", title: "Destination Research", status: "skipped", started_at: null, completed_at: null, duration_ms: null, attempts: 0, source: "execution decision", data: {} },
    { id: "planner", title: "Planner / Candidate", status: status === "planning" ? "running" : status === "failed" ? "failed" : "completed", started_at: null, completed_at: null, duration_ms: 15400, attempts: 1, source: "progress.events", data: { candidate: { activities: [] } } },
    { id: "user_decision", title: "Awaiting User Decision", status: status === "awaiting_confirmation" ? "running" : "completed", started_at: null, completed_at: null, duration_ms: null, attempts: 0, source: "run", data: { status, base_trip_version: 18, accepted_trip_version: status === "accepted" ? 19 : null, feedback_persisted: status === "rejected" } },
  ],
});
function client(runs = [run()]): MonitorClient {
  return { runs: vi.fn().mockResolvedValue(runs), trace: vi.fn().mockImplementation(async (id: string) => trace(id, runs.find((item) => item.id === id)?.status)) };
}
function mount(source: MonitorClient, entry = "/dev/agent-monitor?split=0", intervalMs = 10000) {
  const view = render(<MemoryRouter initialEntries={[entry]}><AgentMonitor client={source} intervalMs={intervalMs} /></MemoryRouter>);
  fireEvent.click(screen.getByRole("checkbox", { name: "自动跟随阶段" }));
  return view;
}
it("shows an empty state and offers the ordinary trip UI", async () => {
  mount(client([]));
  expect(await screen.findByText("暂无可展示的 Agent 运行记录")).toBeVisible();
  expect(screen.getByRole("checkbox", { name: "跟随最新运行" })).toBeChecked();
});
it("selects stages and distinguishes skipped and unavailable fields", async () => {
  mount(client());
  await screen.findByText("请求 real-run-a");
  fireEvent.click(screen.getByRole("button", { name: /上下文构建/ }));
  expect(screen.getByText("上下文项目： 1 / 2")).toBeVisible();
  expect(screen.getByText("导航预计到达时间")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /目的地研究/ }));
  expect(screen.getByText("↷ 本次路径未执行此阶段。")).toBeVisible();
});
it("replays an older run without following the latest", async () => {
  const source = client([run("new-run"), run("old-run", "accepted")]);
  mount(source);
  await screen.findByText("请求 new-run");
  fireEvent.change(screen.getByRole("combobox", { name: "历史运行" }), { target: { value: "old-run" } });
  await screen.findByText("请求 old-run");
  expect(screen.getByRole("checkbox", { name: "跟随最新运行" })).not.toBeChecked();
  expect(screen.getByText(/历史回放/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: /用户决策/ }));
  expect(screen.getByText(/行程版本 18 → 19/)).toBeVisible();
});
it("opens a bookmarked historical run even outside the recent list", async () => {
  mount(client(), "/dev/agent-monitor?run=archived-run");
  expect(await screen.findByText("请求 archived-run")).toBeVisible();
  expect(screen.getByRole("checkbox", { name: "跟随最新运行" })).not.toBeChecked();
});
it("follows a new live run on the next poll", async () => {
  const source = client();
  mount(source, "/dev/agent-monitor?run=real-run-a", 50);
  fireEvent.click(screen.getByRole("checkbox", { name: "跟随最新运行" }));
  await screen.findByText("请求 real-run-a");
  vi.mocked(source.runs).mockResolvedValue([run("newest-run", "planning")]);
  vi.mocked(source.trace).mockImplementation(async (id) => trace(id, "planning"));
  expect(await screen.findByText("请求 newest-run")).toBeVisible();
  expect(screen.getByRole("button", { name: /规划与候选方案/ })).toHaveAttribute("data-status", "running");
});
it("retains the displayed trace after transient polling errors", async () => {
  const source = client();
  mount(source, undefined, 60);
  await screen.findByText("请求 real-run-a");
  vi.mocked(source.runs).mockRejectedValue(new Error("temporary network failure"));
  expect(await screen.findByRole("alert")).toHaveTextContent("保留上次结果");
  expect(screen.getByText("请求 real-run-a")).toBeVisible();
});
it("does not allow a stale request for a previous run to overwrite selection", async () => {
  const source = client([run("first-run"), run("second-run")]);
  let resolveOld: (value: MonitorTrace) => void = () => {};
  vi.mocked(source.trace).mockImplementation((id) => id === "first-run" ? new Promise((resolve) => { resolveOld = resolve; }) : Promise.resolve(trace(id)));
  mount(source);
  await waitFor(() => expect(source.trace).toHaveBeenCalledWith("first-run", expect.any(AbortSignal)));
  fireEvent.change(screen.getByRole("combobox", { name: "历史运行" }), { target: { value: "second-run" } });
  await screen.findByText("请求 second-run");
  await act(async () => { resolveOld(trace("first-run")); });
  expect(screen.queryByText("请求 first-run")).not.toBeInTheDocument();
});
it("presentation mode hides developer JSON and follows the running node", async () => {
  mount(client());
  await screen.findByText("请求 real-run-a");
  expect(screen.getByText(/开发者详情/)).toBeVisible();
  fireEvent.click(screen.getByRole("checkbox", { name: "自动跟随阶段" }));
  fireEvent.click(screen.getByRole("button", { name: "演示模式" }));
  await waitFor(() => expect(screen.getByRole("button", { name: /用户决策/ })).toHaveAttribute("aria-pressed", "true"));
  expect(screen.queryByText(/开发者详情/)).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /打开旅行工作台/ })).not.toBeInTheDocument();
  expect(screen.getByText("Agent 权限边界")).toBeVisible();
});
it("shows failed run errors and real tool summaries", async () => {
  const source = client([run("failed-run", "failed")]);
  const failed = trace("failed-run", "failed");
  failed.error = { code: "planner_timeout", message: "模型超时", stage: "planner" };
  failed.tools = [{ id: "call-one", stage: "planner", provider: "GLM", purpose: "Generate Candidate", status: "failed", started_at: "2026-09-29T10:00:01Z", duration_ms: 180000, input: {}, output: { error_code: "planner_timeout" } }];
  vi.mocked(source.trace).mockResolvedValue(failed);
  mount(source);
  await screen.findByText("请求 failed-run");
  expect(screen.getByRole("status")).toHaveTextContent("planner_timeout");
  fireEvent.click(screen.getByRole("button", { name: /GLM 生成候选方案/ }));
  expect(within(screen.getByRole("region", { name: "步骤详情" })).getByText("180.00 秒")).toBeVisible();
  expect(screen.getByText("输出摘要")).toBeVisible();
});
it("shows a persisted rejection without claiming an itinerary change", async () => {
  mount(client([run("reject-run", "rejected")]));
  await screen.findByText("请求 reject-run");
  fireEvent.click(screen.getByRole("button", { name: /用户决策/ }));
  expect(screen.getByText(/方案已拒绝 · 反馈 已保存/)).toBeVisible();
  expect(screen.queryByText(/正式行程已更新/)).not.toBeInTheDocument();
});

it("offers the real conversation and monitor side by side", async () => {
  mount(client([]), "/dev/agent-monitor?trip=trip-a");
  expect(screen.getByTitle("旅行总管实时对话")).toHaveAttribute("src", "/dev/agent-conversation/trip-a");
  expect(await screen.findByText("暂无可展示的 Agent 运行记录")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "独立监控" }));
  expect(screen.queryByTitle("旅行总管实时对话")).not.toBeInTheDocument();
});

it("observes an outgoing dialogue immediately and never reuses an old run for an answer", async () => {
  let listener: ((event: MessageEvent<DialogueObservation>) => void) | null = null;
  vi.stubGlobal("BroadcastChannel", class {
    constructor(name: string) { expect(name).toBe(MONITOR_CHANNEL); }
    set onmessage(handler: (event: MessageEvent<DialogueObservation>) => void) { listener = handler; }
    close() {}
  });
  const view = mount(client());
  await screen.findByText("请求 real-run-a");
  await act(async () => { listener?.({ data: { type: "request_started", requestId: "actual-request", message: "杭州有什么文化特色？", tripId: "trip-a", at: new Date().toISOString() } } as MessageEvent<DialogueObservation>); });
  expect(screen.getByRole("region", { name: "实时对话请求" })).toHaveTextContent("杭州有什么文化特色？");
  expect(screen.queryByText("请求 real-run-a")).not.toBeInTheDocument();
  expect(screen.getByText(/具体内部阶段尚未返回/)).toBeVisible();
  await act(async () => { listener?.({ data: { type: "request_completed", requestId: "actual-request", assistant: "实际回答", runtimeTrace: ["interpret_goal", "generate_interaction"], at: new Date().toISOString() } } as MessageEvent<DialogueObservation>); });
  fireEvent.click(screen.getByText("查看本次回答"));
  expect(screen.getByText("实际回答")).toBeVisible();
  expect(screen.getByText(/未创建新的规划运行/)).toBeVisible();
  expect(screen.getByText(/理解对话目标/)).toBeVisible();
  view.unmount(); vi.unstubAllGlobals();
});

it("keeps a dialogue bound to its exact run even when another run is newer", async () => {
  let listener: ((event: MessageEvent<DialogueObservation>) => void) | null = null;
  vi.stubGlobal("BroadcastChannel", class {
    set onmessage(handler: (event: MessageEvent<DialogueObservation>) => void) { listener = handler; }
    close() {}
  });
  const source = client([run("unrelated-newest"), run("dialogue-run")]);
  const view = mount(source, undefined, 50);
  await screen.findByText("请求 unrelated-newest");
  const emit = async (event: Partial<DialogueObservation>) => act(async () => listener?.({ data: { at: new Date().toISOString(), ...event } } as MessageEvent<DialogueObservation>));
  await emit({ type: "request_started", requestId: "current", tripId: "trip-a", message: "调整下午" });
  await emit({ type: "request_completed", requestId: "current", runId: "dialogue-run" });
  await waitFor(() => expect(source.trace).toHaveBeenCalledWith("dialogue-run", expect.any(AbortSignal)));
  fireEvent.click(screen.getByRole("button", { name: /用户请求/ }));
  expect(await screen.findByText("请求 dialogue-run")).toBeVisible();
  await waitFor(() => expect(source.trace).toHaveBeenCalledWith("dialogue-run", expect.any(AbortSignal)));
  expect(screen.queryByText("请求 unrelated-newest")).not.toBeInTheDocument();
  await emit({ type: "request_completed", requestId: "previous", runId: "unrelated-newest" });
  expect(screen.getByText("请求 dialogue-run")).toBeVisible();
  view.unmount(); vi.unstubAllGlobals();
});

it("polls actual Companion stages while the assistant request is still pending", async () => {
  let listener: ((event: MessageEvent<DialogueObservation>) => void) | null = null;
  vi.stubGlobal("BroadcastChannel", class {
    set onmessage(handler: (event: MessageEvent<DialogueObservation>) => void) { listener = handler; }
    close() {}
  });
  const source = client([]);
  const generate = { sequence: 1, stage: "generate", status: "running", at: "2026-09-29T10:00:01Z", duration_ms: null };
  source.dialogue = vi.fn().mockResolvedValue({ status: "running", source: "process_local", events: [generate] });
  const view = mount(source, undefined, 50);
  await screen.findByText("暂无可展示的 Agent 运行记录");
  await act(async () => listener?.({ data: { type: "request_started", requestId: "current", sessionId: "session", messageId: "message", message: "杭州文化", at: new Date().toISOString() } } as MessageEvent<DialogueObservation>));
  const region = await screen.findByRole("region", { name: "对话 Agent 执行阶段" });
  expect(within(region).getByText("生成回答与建议")).toBeVisible();
  expect(within(region).getByText("执行中")).toBeVisible();
  expect(screen.queryByText("规划与候选方案")).not.toBeInTheDocument();
  vi.mocked(source.dialogue).mockResolvedValue({ status: "completed", source: "process_local", events: [generate, { ...generate, sequence: 2, status: "completed", duration_ms: 2100 }] });
  await waitFor(() => expect(within(region).getByText("已完成")).toBeVisible());
  expect(within(region).getByText(/2.10 秒/)).toBeVisible();
  view.unmount(); vi.unstubAllGlobals();
});

it("automatically advances to the currently running stage", async () => {
  const source = client([run("live-run", "planning")]);
  mount(source);
  fireEvent.click(screen.getByRole("checkbox", { name: "自动跟随阶段" }));
  await waitFor(() => expect(screen.getByRole("button", { name: /规划与候选方案/ })).toHaveAttribute("aria-pressed", "true"));
  fireEvent.click(screen.getByRole("button", { name: /上下文构建/ }));
  expect(screen.getByRole("checkbox", { name: "自动跟随阶段" })).not.toBeChecked();
});
