import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { App } from "./App";
import { LocalTripPlanningRepository } from "./data/mockTripPlanningRepository";

describe("planner workbench", () => {
  beforeEach(() => localStorage.clear());

  it("opens the fixed demo route and synchronizes the selected activity", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/trips/demo/planner"]}><App repository={new LocalTripPlanningRepository(localStorage)} /></MemoryRouter>);

    expect(await screen.findByText("湖滨散步与城市夜色")).toBeInTheDocument();
    expect(screen.getByTestId("map-fallback")).toBeInTheDocument();
    await user.click(screen.getByText("西湖·断桥").closest("button")!);
    expect(await screen.findByTestId("inspector")).toHaveTextContent("西湖·断桥");

    await user.click(screen.getByRole("tab", { name: /9月6日/ }));
    expect(await screen.findByText("山林茶村与从容返程")).toBeInTheDocument();
  });

  it("adds a mock place and updates the budget", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={["/trips/demo/planner"]}><App repository={new LocalTripPlanningRepository(localStorage)} /></MemoryRouter>);
    await screen.findByText("湖滨散步与城市夜色");
    await user.click(screen.getByRole("button", { name: "从候选地点加入" }));
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
});
