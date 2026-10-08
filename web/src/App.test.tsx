import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { App } from "./App";
import { LocalTripPlanningRepository } from "./data/mockTripPlanningRepository";
import { formatFen } from "./utils/planner";
import type { PlanRevision, PlanningRun } from "./domain/types";

describe("planner workbench", () => {
  beforeEach(() => localStorage.clear());

  it("opens the fixed demo route and synchronizes the selected activity", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/trips/demo/planner"]}><App repository={new LocalTripPlanningRepository(localStorage)} /></MemoryRouter>);

    expect(await screen.findByText("湖滨散步与城市夜色")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "地图" }));
    expect(screen.getByTestId("map-fallback")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "行程" }));
    await user.click(screen.getByText("西湖·断桥").closest("button")!);
    expect(await screen.findByTestId("inspector")).toHaveTextContent("西湖·断桥");

    await user.click(screen.getByRole("tab", { name: /9月6日/ }));
    expect(await screen.findByText("山林茶村与从容返程")).toBeInTheDocument();
  });

  it("adds a mock place and updates the budget", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/trips/demo/planner"]}><App repository={new LocalTripPlanningRepository(localStorage)} /></MemoryRouter>);
    await screen.findByText("湖滨散步与城市夜色");
    await user.click(screen.getByRole("button", { name: "添加地点" }));
    expect(screen.getByTestId("places-drawer")).toBeInTheDocument();
    const candidate = screen.getByText("雷峰塔").closest("article")!;
    await user.click(candidate.querySelector("button")!);
    await waitFor(() => expect(screen.getByTestId("budget-summary")).toHaveTextContent("¥120"));
  });

  it("selects a verified city and accommodation POI during trip setup", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/trips/new"]}><App repository={new LocalTripPlanningRepository(localStorage)} /></MemoryRouter>);
    await user.type(screen.getByRole("textbox", { name: "目的地城市" }), "南昌");
    await user.click(await screen.findByRole("button", { name: /南昌市.*360100/ }));
    await user.click(screen.getByText("住宿与更多偏好（可选）"));
    const accommodation = screen.getByPlaceholderText("搜索南昌市酒店或民宿");
    await user.type(accommodation, "酒店");
    await user.click(screen.getByRole("button", { name: "搜索住宿" }));
    await user.click(await screen.findByRole("button", { name: /中心酒店/ }));
    expect(screen.getByText(/已选择高德住宿 POI/)).toHaveTextContent("测试路 1 号");
  });

  it("loads and persists the structured planning profile", async () => {
    const user = userEvent.setup();
    const repository = new LocalTripPlanningRepository(localStorage);
    const updatePreferences = vi.spyOn(repository, "updateTripPreferences");
    render(<MemoryRouter initialEntries={["/trips/demo/edit"]}><App repository={repository} /></MemoryRouter>);

    expect(await screen.findByRole("heading", { name: "智能规划偏好" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("行程节奏"), "relaxed");
    await user.click(screen.getByLabelText("历史"));
    await user.clear(screen.getByLabelText("最长连续步行（分钟）"));
    await user.type(screen.getByLabelText("最长连续步行（分钟）"), "45");
    await user.type(screen.getByLabelText("补充要求"), "下午保留机动时间");
    await user.click(screen.getByRole("button", { name: "保存旅行设置" }));

    await waitFor(() => expect(updatePreferences).toHaveBeenCalledWith("demo", expect.objectContaining({
      pace: "relaxed",
      interestCategories: expect.arrayContaining(["history"]),
      maxWalkingMinutes: 45,
      freeTextRequirements: "下午保留机动时间",
    })));
  });

  it("edits an activity and moves it to another day", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/trips/demo/planner"]}><App repository={new LocalTripPlanningRepository(localStorage)} /></MemoryRouter>);
    await screen.findByText("湖滨散步与城市夜色");
    await user.click(screen.getByText("西湖·断桥").closest("button")!);
    await user.click(await screen.findByRole("button", { name: "编辑活动" }));
    const nameInput = screen.getByRole("textbox", { name: "显示名称" });
    await user.clear(nameInput);
    await user.type(nameInput, "西湖晨间散步");
    const costInput = screen.getByRole("textbox", { name: "预计费用（元）" });
    await user.clear(costInput);
    await user.type(costInput, "12.34");
    await user.click(screen.getByRole("checkbox", { name: /固定开始时间/ }));
    await user.click(screen.getByRole("button", { name: "保存修改" }));
    expect((await screen.findAllByText("西湖晨间散步")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("¥12").length).toBeGreaterThan(0);

    await user.selectOptions(screen.getByRole("combobox", { name: "移动到其他日期" }), "day-2");
    await user.click(screen.getByRole("button", { name: "移到开头" }));
    expect(await screen.findByText("山林茶村与从容返程")).toBeInTheDocument();
    expect(screen.getAllByText("西湖晨间散步").length).toBeGreaterThan(0);
  });

  it("asks before closing an activity form with unsaved changes", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/trips/demo/planner"]}><App repository={new LocalTripPlanningRepository(localStorage)} /></MemoryRouter>);
    await screen.findByText("湖滨散步与城市夜色");
    await user.click(screen.getByText("西湖·断桥").closest("button")!);
    await user.click(await screen.findByRole("button", { name: "编辑活动" }));
    await user.type(screen.getByRole("textbox", { name: "备注" }), "未保存内容");
    await user.click(screen.getByRole("button", { name: "关闭详情" }));
    expect(screen.getByRole("alert")).toHaveTextContent("放弃未保存的修改");
    await user.click(screen.getByRole("button", { name: "继续编辑" }));
    expect(screen.getByRole("textbox", { name: "备注" })).toHaveValue("未保存内容");
  });

  it("keeps generated AI runs in the visible history", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/trips/demo/planner"]}><App repository={new LocalTripPlanningRepository(localStorage)} /></MemoryRouter>);
    await screen.findByText("湖滨散步与城市夜色");
    await user.click(screen.getByRole("button", { name: "打开旅程总管" }));
    await user.type(await screen.findByRole("textbox", { name: "告诉旅程总管" }), "请调整第2天下午的行程，减少步行。");
    await waitFor(() => expect(screen.getByRole("button", { name: "发送需求" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "发送需求" }));
    expect(await screen.findByText("对话与方案记录")).toBeInTheDocument();
    expect(screen.getAllByText(/请调整第2天下午/).length).toBeGreaterThan(0);
  });
});


it("saves completion without creating an execution session", async () => {
  localStorage.clear();
  const repository = new LocalTripPlanningRepository(localStorage);
  const start = vi.spyOn(repository, "startTripExecution");
  const update = vi.spyOn(repository, "updateActivity");
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={["/trips/demo"]}><App repository={repository} /></MemoryRouter>);
  await user.click((await screen.findByText("西湖·断桥")).closest("button")!);
  await user.click(screen.getByRole("button", { name: "完成" }));
  await waitFor(() => expect(update).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ status: "completed" })));
  await screen.findByRole("button", { name: "恢复为待游玩" });
  expect(start).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "开始旅行" })).not.toBeInTheDocument();
});

it("redirects the old assistant link to the unified trip directory", async () => {
  render(<MemoryRouter initialEntries={["/assistant"]}><App repository={new LocalTripPlanningRepository(localStorage)} /></MemoryRouter>);
  expect(await screen.findByRole("heading", { name: "从一座城市开始规划" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "旅程总管" })).toBeInTheDocument();
});

it("opens the monitor from the trip manager before a trip exists", async () => {
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={["/trips"]}><App repository={new LocalTripPlanningRepository(localStorage)} /></MemoryRouter>);
  await user.click(screen.getByRole("button", { name: "旅程总管" }));
  const link = await screen.findByRole("link", { name: "打开监控台" });
  expect(link).toHaveAttribute("href", "/dev/agent-monitor");
  expect(link).toHaveAttribute("target", "_blank");
});

it("shows the pre-trip conversation beside an unfiltered monitor", async () => {
  render(<MemoryRouter initialEntries={["/dev/agent-conversation"]}><App repository={new LocalTripPlanningRepository(localStorage)} /></MemoryRouter>);
  expect(await screen.findByText("创建旅行前 · 旅程总管")).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "告诉旅程总管" })).toBeInTheDocument();
  expect(screen.queryByText("暂无旅行，请先在完整工作台创建旅行。")).not.toBeInTheDocument();
});

it("keeps the saved trip when saving preferences fails and retries without duplicating it", async () => {
  localStorage.clear();
  const repository = new LocalTripPlanningRepository(localStorage);
  const trip = await repository.getTrip("demo");
  const create = vi.spyOn(repository, "createTrip").mockResolvedValue(trip);
  const preferences = vi.spyOn(repository, "updateTripPreferences");
  preferences.mockRejectedValueOnce(new Error("偏好暂未保存，请重试"));
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={["/trips/new"]}><App repository={repository} /></MemoryRouter>);
  await user.type(screen.getByRole("textbox", { name: "目的地城市" }), "南昌");
  await user.click(await screen.findByRole("button", { name: /南昌市.*360100/ }));
  await user.click(screen.getByRole("button", { name: "创建旅程并让 AI 规划" }));
  await screen.findByText("偏好暂未保存，请重试");
  await user.click(screen.getByRole("button", { name: "创建旅程并让 AI 规划" }));
  await screen.findByRole("complementary", { name: "旅程总管" });
  expect(create).toHaveBeenCalledTimes(1);
});

it.each([false, true])("opens the committed AI plan and preserves it after remount (refresh failure: %s)", async (failRefresh) => {
  localStorage.clear();
  const repository = new LocalTripPlanningRepository(localStorage);
  const before = await repository.getDays("demo");
  const target = before[1].activities[0];
  const run: PlanningRun = { id: "apply-run", tripId: "demo", runType: "replan", status: "awaiting_confirmation", userRequest: "第二天改到13点，调整费用", tokenUsage: 0 };
  const revision: PlanRevision = { id: "apply-revision", planningRunId: run.id, status: "pending", reason: run.userRequest,
    activities: [{ candidateId: "change", dayDate: before[1].date, placeCandidateId: target.placeId, plannedStartTime: "13:00", durationMinutes: target.durationMinutes, estimatedCostFen: 2345, transportModeToHere: "driving", reason: "下午出发", locked: true }],
    differenceSummary: {}, validationResult: { valid: true }, sourceIds: [] };
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([run]);
  vi.spyOn(repository, "getPlanRevision").mockResolvedValue(revision);
  const readDays = vi.spyOn(repository, "getDays");
  const decide = vi.spyOn(repository, "decidePlanningRun").mockImplementation(async () => {
    // Persist through the repository boundary, not by changing component state.
    await repository.updateActivity(target.id, { version: target.version, scheduledTime: "13:00", estimatedCostFen: 2345, scheduleLocked: true });
    await repository.recalculateRoute(before[1].id, "driving");
    if (failRefresh) readDays.mockRejectedValueOnce(new Error("网络暂时不可用"));
    return { run: { ...run, status: "accepted" }, revision: { ...revision, status: "accepted" } };
  });
  const user = userEvent.setup();
  const renderApp = (repo = repository) => render(<MemoryRouter initialEntries={["/trips/demo"]}><App repository={repo} /></MemoryRouter>);
  const first = renderApp();
  await user.click(await screen.findByRole("button", { name: "地图" }));
  await user.click(screen.getByRole("button", { name: "打开旅程总管" }));
  await user.click(screen.getByText("对话与方案记录"));
  await user.click(await screen.findByRole("button", { name: "确认并应用" }));
  if (failRefresh) {
    expect(await screen.findByRole("alert")).toHaveTextContent("方案已保存，但正式行程读取失败");
    expect(screen.queryByText("无法打开旅行")).not.toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "旅程总管" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重新加载正式行程" }));
  }
  await waitFor(() => expect(screen.queryByRole("complementary", { name: "旅程总管" })).not.toBeInTheDocument());
  expect(screen.getByRole("tab", { name: /9月6日/ })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("button", { name: "行程" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText(target.name, { selector: ".timeline-card strong" }).closest("button")).toHaveTextContent("13:00");
  expect(screen.getByText(/^正式行程已更新/)).toBeInTheDocument();
  expect(screen.getByTestId("budget-summary")).toHaveTextContent(formatFen(before[1].activities.reduce((sum, item) => sum + item.estimatedCostFen, 0) - target.estimatedCostFen + 2345));
  expect(screen.getByRole("combobox", { name: "交通" })).toHaveValue("driving");
  expect(decide).toHaveBeenCalledTimes(1);
  expect((await repository.getDays("demo"))[0]).toEqual(before[0]);
  first.unmount();
  renderApp(new LocalTripPlanningRepository(localStorage));
  await user.click(await screen.findByRole("tab", { name: /9月6日/ }));
  expect(screen.getByText(target.name, { selector: ".timeline-card strong" }).closest("button")).toHaveTextContent("13:00");
});

it("updates an already open itinerary when another client accepts new places", async () => {
  localStorage.clear();
  const repository = new LocalTripPlanningRepository(localStorage);
  const trip = await repository.getTrip("demo");
  let version = 1;
  vi.spyOn(repository, "getTrip").mockImplementation(async () => ({ ...trip, version }));
  const days = await repository.getDays("demo");
  const fresh = structuredClone(days);
  fresh[0].activities[0] = { ...fresh[0].activities[0], id: "new-activity", placeId: "new-place", name: "新方案中的钱王祠", scheduledTime: "11:00" };
  const reads = vi.spyOn(repository, "getDays");
  render(<MemoryRouter initialEntries={["/trips/demo"]}><App repository={repository} /></MemoryRouter>);
  await screen.findByText("西湖·断桥");
  reads.mockResolvedValue(fresh);
  version = 2;
  fireEvent.focus(window);
  expect(await screen.findByText("新方案中的钱王祠")).toBeInTheDocument();
  expect(screen.queryByText("西湖·断桥")).not.toBeInTheDocument();
  expect(screen.getByText("新方案中的钱王祠").closest("button")).toHaveTextContent("11:00");
  expect(await screen.findByText("正式行程有新修改，已同步到当前页面")).toBeInTheDocument();
});

it("does not let an in-flight background refresh erase an activity draft", async () => {
  localStorage.clear();
  const repository = new LocalTripPlanningRepository(localStorage);
  const trip = await repository.getTrip("demo");
  const days = await repository.getDays("demo");
  let version = 1;
  vi.spyOn(repository, "getTrip").mockImplementation(async () => ({ ...trip, version }));
  const reads = vi.spyOn(repository, "getDays");
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={["/trips/demo"]}><App repository={repository} /></MemoryRouter>);
  await screen.findByText("西湖·断桥");
  let finishRead!: (value: typeof days) => void;
  reads.mockImplementationOnce(() => new Promise((resolve) => { finishRead = resolve; }));
  version = 2;
  fireEvent.focus(window);
  await waitFor(() => expect(finishRead).toBeDefined());
  await user.click(screen.getByText("西湖·断桥").closest("button")!);
  await user.click(screen.getByRole("button", { name: "编辑活动" }));
  await user.type(screen.getByRole("textbox", { name: "备注" }), "保留这段未保存的输入");
  await act(async () => finishRead(structuredClone(days)));
  expect(screen.getByRole("textbox", { name: "备注" })).toHaveValue("保留这段未保存的输入");
});
