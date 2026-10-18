import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { AiPlannerPanel } from "./AiPlannerPanel";
import { LocalTripPlanningRepository } from "../data/mockTripPlanningRepository";
import type { AssistantSession, AssistantStreamEvent, PlanningRun } from "../domain/types";

const pending: PlanningRun = { id: "saved-run", tripId: "demo", runType: "initial_plan", status: "awaiting_clarification", userRequest: "规划周末旅行", tokenUsage: 0, pendingInterrupt: { questions: ["你更喜欢轻松还是紧凑？"] } };

function setup(repository: LocalTripPlanningRepository) {
  return render(<AiPlannerPanel open tripId="demo" selectedDayId="day-1" days={[]} candidates={[]} repository={repository} onClose={() => undefined} onAccepted={async () => undefined} />);
}

async function openPlanningHistory() {
  await userEvent.click(screen.getByText("对话与方案记录"));
}

beforeEach(() => localStorage.clear());

it("shows analysis then growing answer before the streaming request completes", async () => {
  const session: AssistantSession = { id: "stream", trip_id: "demo", latest_run_id: null, pending_action: null, messages: [] };
  let onEvent!: (event: AssistantStreamEvent) => void;
  let finish!: (value: AssistantSession) => void;
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), {
    getAssistantSession: vi.fn().mockResolvedValue(session),
    sendAssistantMessage: vi.fn(),
    streamAssistantMessage: vi.fn((_id, _message, _messageId, callback) => {
      onEvent = callback;
      return new Promise<AssistantSession>((resolve) => { finish = resolve; });
    }),
  });
  setup(repository);
  await waitFor(() => expect(screen.getByRole("textbox", { name: "告诉旅程总管" })).toBeEnabled());
  const input = screen.getByRole("textbox", { name: "告诉旅程总管" });
  fireEvent.change(input, { target: { value: "为什么会这样安排？" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await waitFor(() => expect(repository.streamAssistantMessage).toHaveBeenCalled());
  act(() => onEvent({ type: "analysis_delta", delta: "结合区域与节奏。" }));
  expect(screen.getByText("结合区域与节奏。")).toBeVisible();
  expect(screen.getByText("Thinking · 正在分析")).toBeInTheDocument();
  act(() => onEvent({ type: "answer_delta", delta: "第一天集中钟山。" }));
  await waitFor(() => expect(screen.getByText("第一天集中钟山。")).toBeVisible());
  expect(screen.getByRole("textbox", { name: "告诉旅程总管" })).toBeDisabled();
  act(() => onEvent({ type: "answer_delta", delta: "下午转入室内。" }));
  await waitFor(() => expect(screen.getByText("第一天集中钟山。下午转入室内。")).toBeVisible());
  act(() => onEvent({ type: "reset" }));
  expect(screen.queryByText("第一天集中钟山。下午转入室内。")).toBeNull();
  await act(async () => finish({ ...session, messages: [{ id: "complete", user: "为什么会这样安排？", assistant: "完成后的解释。",
    companion_result: { response_text: "完成后的解释。", analysis_summary: "结合区域与节奏。", goal_type: "explanation", status: "completed",
      suggestions: [], resolved_suggestion_refs: [], runtime_trace: [] } }] }));
  expect(screen.getByText("完成后的解释。")).toBeVisible();
  expect(screen.getByText("Thinking · 分析摘要")).toBeInTheDocument();
  expect(repository.sendAssistantMessage).not.toHaveBeenCalled();
});

it("renders a Companion reply with routing metadata and no planning run", async () => {
  const session: AssistantSession = { id: "companion", trip_id: "demo", latest_run_id: null, pending_action: null,
    messages: [{ id: "turn", user: "西湖有什么历史？", assistant: "可以先了解西湖的人文历史。", run_id: null,
      companion_result: { response_text: "可以先了解西湖的人文历史。", goal_type: "explanation", status: "completed",
        suggestions: [], resolved_suggestion_refs: [], explanation: null, runtime_trace: ["interpret_goal", "prepare_conversation_persistence"],
        answer_evidence_refs: ["knowledge_1"], grounding_status: "citations_validated",
        grounding_limitations: ["claim_entailment_not_verified"], knowledge_retrieval: { status: "available", outcome: "available", retrieval_mode: "lexical" },
        knowledge_evidence: [{ evidence_ref: "knowledge_1", text: "文化景观资料。", source_reference: "https://whc.unesco.org/en/list/1334",
          knowledge_type: "history_culture", scope: "stable", document_id: "history", chunk_id: "chunk" }] },
      goal_routing: { goal_type: "explanation", confidence: 0.94, target_runtime: "companion", mutation_requested: false,
        trip_context_required: false, knowledge_required: true, live_fact_likely_required: false,
        referenced_entities: [], referenced_previous_decision: false, clarification_needed: false, signals: ["companion_explanation"] } }] };
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session) });
  const listRuns = vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([]);
  const getRun = vi.spyOn(repository, "getPlanningRun");
  const createRun = vi.spyOn(repository, "createPlanningRun");
  const planningContext = vi.spyOn(repository, "getPlanningContext");
  setup(repository);
  expect(screen.getByText("今天想聊点什么？")).toBeInTheDocument();
  expect(screen.queryByText(/目的地、日期和预算/)).not.toBeInTheDocument();
  expect(await screen.findByText("可以先了解西湖的人文历史。")).toBeInTheDocument();
  expect(screen.getAllByText("可以先了解西湖的人文历史。")).toHaveLength(1);
  expect(getRun).not.toHaveBeenCalled();
  expect(createRun).not.toHaveBeenCalled();
  expect(listRuns).not.toHaveBeenCalled();
  expect(planningContext).not.toHaveBeenCalled();
});

it("only shows rejection feedback actually retrieved for the current planning run", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([{
    ...pending, status: "planning",
    decisionMemory: { count: 1, feedback: [{ sourceRevisionId: "revision-1", reasonCode: "too_rushed", reasonText: "文化场馆安排得太短" }] },
  }]);
  vi.spyOn(repository, "getPlanningRun").mockResolvedValue({
    ...pending, status: "planning",
    decisionMemory: { count: 1, feedback: [{ sourceRevisionId: "revision-1", reasonCode: "too_rushed", reasonText: "文化场馆安排得太短" }] },
  });
  setup(repository);
  await openPlanningHistory();
  expect(await screen.findByLabelText("已参考上次反馈")).toHaveTextContent("文化场馆安排得太短");
});

it("immediately echoes homepage input while the assistant request is pending", async () => {
  const session: AssistantSession = { id: "home", trip_id: null, messages: [], pending_action: null, latest_run_id: null };
  let finish!: (value: AssistantSession) => void;
  const send = vi.fn().mockImplementation(() => new Promise<AssistantSession>((resolve) => { finish = resolve; }));
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session), sendAssistantMessage: send });
  render(<AiPlannerPanel open days={[]} candidates={[]} repository={repository} onClose={() => undefined} onAccepted={async () => undefined} />);
  const input = screen.getByRole("textbox", { name: "告诉旅程总管" });
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { value: "香格里拉三天两晚" } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(screen.getByText("香格里拉三天两晚")).toBeInTheDocument();
  expect(input).toHaveValue("");
  expect(screen.getByRole("status")).toHaveTextContent("正在回复");
  expect(screen.queryByText(/核对.*日期.*预算/)).not.toBeInTheDocument();
  fireEvent.keyDown(input, { key: "Enter" });
  expect(send).toHaveBeenCalledTimes(1);
  await act(async () => finish({ ...session, messages: [{ id: "one", user: "香格里拉三天两晚", assistant: "请提供出发日期和预算" }] }));
  expect(screen.getAllByText("香格里拉三天两晚")).toHaveLength(1);
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

it("retains a failed message and reuses its id when retried", async () => {
  const session: AssistantSession = { id: "home", trip_id: null, messages: [], pending_action: null, latest_run_id: null };
  const send = vi.fn().mockRejectedValueOnce(new Error("连接中断")).mockResolvedValue({ ...session, messages: [{ id: "one", user: "三天两晚", assistant: "收到" }] });
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session), sendAssistantMessage: send });
  render(<AiPlannerPanel open days={[]} candidates={[]} repository={repository} onClose={() => undefined} onAccepted={async () => undefined} />);
  const input = screen.getByRole("textbox", { name: "告诉旅程总管" });
  await waitFor(() => expect(input).toBeEnabled());
  fireEvent.change(input, { target: { value: "三天两晚" } });
  fireEvent.keyDown(input, { key: "Enter" });
  await screen.findByText("本次请求尚未确认成功，内容已保留，可重试发送。");
  expect(input).toHaveValue("三天两晚");
  fireEvent.keyDown(input, { key: "Enter" });
  await screen.findByText("收到");
  expect(send.mock.calls[0][2]).toEqual(send.mock.calls[1][2]);
});

it("continues polling after a temporary status request failure", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([{ ...pending, status: "researching" }]);
  const poll = vi.spyOn(repository, "getPlanningRun").mockRejectedValueOnce(new Error("临时连接中断"))
    .mockResolvedValue({ ...pending, status: "answered", responseText: "连接恢复后的正式回答" });
  setup(repository);
  await openPlanningHistory();
  await screen.findByRole("status");
  await screen.findByText("连接恢复后的正式回答", {}, { timeout: 5000 });
  expect(poll).toHaveBeenCalledTimes(2);
  expect(screen.queryByText("临时连接中断")).not.toBeInTheDocument();
});

it("renders the authoritative tool answer once in its conversation turn", async () => {
  const session: AssistantSession = { id: "session", trip_id: "demo", latest_run_id: "answer", pending_action: null, messages: [{ id: "turn", user: "第二天怎么走？", assistant: "调度确认收到需求", run_id: "answer" }] };
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session) });
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([{ ...pending, id: "answer", status: "answered", responseText: "建议二：午后增加茶园。" }]);
  setup(repository);
  await openPlanningHistory();
  await screen.findByText("建议二：午后增加茶园。");
  expect(screen.getAllByText("建议二：午后增加茶园。")).toHaveLength(1);
  expect(screen.queryByText("调度确认收到需求")).not.toBeInTheDocument();
});

it("previews a homepage conversation and opens the created trip only after confirmation", async () => {
  const session: AssistantSession = { id: "home-session", trip_id: null, messages: [], pending_action: null, latest_run_id: null };
  const proposed: AssistantSession = { ...session, messages: [{ id: "message", user: "明年去成都两天", assistant: "请核对日期和预算。" }], pending_action: { id: "action", tool: "create_trip", title: "成都两日游", city: { name: "成都市" }, start_date: "2027-05-01", end_date: "2027-05-02", total_budget_fen: 200000, daily_budget_fen: 100000, preferences: "轻松，美食", summary: "确认后创建旅行。" } };
  const send = vi.fn().mockResolvedValue(proposed);
  const decide = vi.fn().mockResolvedValue({ ...proposed, trip_id: "new-trip", pending_action: null });
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session), sendAssistantMessage: send, decideAssistantAction: decide });
  const changed = vi.fn();
  const user = userEvent.setup();
  render(<AiPlannerPanel open days={[]} candidates={[]} repository={repository} onClose={() => undefined} onAccepted={async () => undefined} onTripChanged={changed} />);
  const input = screen.getByRole("textbox", { name: "告诉旅程总管" });
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(input, "明年去成都两天{Enter}");
  await screen.findByText("成都两日游");
  expect(changed).not.toHaveBeenCalled();
  expect(send).toHaveBeenCalledWith("home-session", "明年去成都两天", expect.any(String), undefined, undefined);
  await user.click(screen.getByRole("button", { name: "确认创建" }));
  await waitFor(() => expect(changed).toHaveBeenCalledWith("new-trip"));
  expect(decide).toHaveBeenCalledWith("home-session", "action", true);
});

it("restores conversation and refreshes the current trip after a confirmed reschedule", async () => {
  const session: AssistantSession = { id: "trip-session", trip_id: "demo", latest_run_id: null, messages: [{ id: "earlier", user: "改到明年", assistant: "可以整体改期。" }], pending_action: { id: "shift", tool: "reschedule_trip", title: "未来的杭州旅行", city: { name: "杭州市" }, start_date: "2027-05-01", end_date: "2027-05-02", total_budget_fen: 200000, daily_budget_fen: 100000, preferences: "", summary: "活动按天移动。" } };
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session), decideAssistantAction: vi.fn().mockResolvedValue({ ...session, pending_action: null }) });
  const changed = vi.fn();
  const user = userEvent.setup();
  render(<AiPlannerPanel open tripId="demo" days={[]} candidates={[]} repository={repository} onClose={() => undefined} onAccepted={async () => undefined} onTripChanged={changed} />);
  await screen.findByText("可以整体改期。");
  await user.click(screen.getByRole("button", { name: "确认改期" }));
  await waitFor(() => expect(changed).toHaveBeenCalledWith("demo"));
});

it("sends initial planning with selection context instead of a hardcoded second-day adjustment", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  const create = vi.spyOn(repository, "createPlanningRun");
  const user = userEvent.setup();
  setup(repository);
  const input = screen.getByRole("textbox", { name: "告诉旅程总管" });
  expect(input).toHaveValue("");
  await waitFor(() => expect(input).toBeEnabled());
  await user.click(screen.getByRole("button", { name: "生成完整行程" }));
  await user.click(screen.getByRole("button", { name: "发送需求" }));
  await waitFor(() => expect(create).toHaveBeenCalledWith("demo", expect.any(String), { runType: "initial_plan", selectedDayId: undefined, selectedActivityId: undefined }));
});

it("restores clarification and immediately displays a returned proposal", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([pending]);
  const answer = vi.spyOn(repository, "answerPlanningRun").mockResolvedValue({ ...pending, status: "awaiting_confirmation" });
  const revision = vi.spyOn(repository, "getPlanRevision");
  const user = userEvent.setup();
  setup(repository);
  await openPlanningHistory();
  await screen.findByText("你更喜欢轻松还是紧凑？");
  expect(screen.getByRole("textbox", { name: "告诉旅程总管" })).toBeEnabled();
  await user.type(screen.getByRole("textbox", { name: "补充回答" }), "轻松");
  await user.click(screen.getByRole("button", { name: "提交补充" }));
  await screen.findByRole("button", { name: "确认并应用" });
  expect(answer).toHaveBeenCalledWith("saved-run", "轻松");
  expect(revision).toHaveBeenCalledWith("saved-run");
});

it("recovers a saved candidate after remount without creating another task", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([{ ...pending, status: "awaiting_confirmation" }]);
  const create = vi.spyOn(repository, "createPlanningRun");
  const first = setup(repository);
  await openPlanningHistory();
  await screen.findByRole("button", { name: "确认并应用" });
  first.unmount();
  setup(repository);
  await openPlanningHistory();
  await screen.findByRole("button", { name: "确认并应用" });
  expect(create).not.toHaveBeenCalled();
});

it("shows planning history failures without blocking Companion chat", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  vi.spyOn(repository, "listPlanningRuns").mockRejectedValue(new Error("历史读取失败"));
  setup(repository);
  await openPlanningHistory();
  expect(await screen.findByRole("alert")).toHaveTextContent("历史读取失败");
  expect(screen.getByRole("textbox", { name: "告诉旅程总管" })).toBeEnabled();
});

it("sends with Enter, inserts a newline with Shift+Enter and ignores Chinese composition", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  const create = vi.spyOn(repository, "createPlanningRun");
  const user = userEvent.setup();
  setup(repository);
  const input = screen.getByRole("textbox", { name: "告诉旅程总管" });
  await waitFor(() => expect(input).toBeEnabled());
  await user.type(input, "我希望这次旅行可以丰富一些");
  await user.keyboard("{Shift>}{Enter}{/Shift}");
  expect(input).toHaveValue("我希望这次旅行可以丰富一些\n");
  expect(create).not.toHaveBeenCalled();
  fireEvent.compositionStart(input);
  fireEvent.keyDown(input, { key: "Enter", code: "Enter" });
  fireEvent.compositionEnd(input);
  fireEvent.keyDown(input, { key: "Enter", code: "Enter", isComposing: true });
  fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
  fireEvent.keyDown(input, { key: "Enter", repeat: true });
  expect(create).not.toHaveBeenCalled();
  await user.keyboard("{Enter}");
  await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
  expect(create).toHaveBeenCalledWith("demo", "我希望这次旅行可以丰富一些", expect.any(Object));
  fireEvent.keyDown(input, { key: "Enter" });
  expect(create).toHaveBeenCalledTimes(1);
});

it("submits a clarification with Enter", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([pending]);
  const answer = vi.spyOn(repository, "answerPlanningRun").mockResolvedValue({ ...pending, status: "awaiting_confirmation" });
  const user = userEvent.setup();
  setup(repository);
  await openPlanningHistory();
  const input = await screen.findByRole("textbox", { name: "补充回答" });
  await user.type(input, "在现有安排上增加人文体验{Enter}");
  await waitFor(() => expect(answer).toHaveBeenCalledWith("saved-run", "在现有安排上增加人文体验"));
});

it("allows questions while a proposal awaits approval and renders the answer without an apply button", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([{ ...pending, status: "awaiting_confirmation" }]);
  const create = vi.spyOn(repository, "createPlanningRun").mockResolvedValue({ ...pending, id: "answer-run", status: "answered", userRequest: "为什么这样安排？", responseText: "上午保留人文游览，午间留出休息，避免连续赶路。" });
  const apply = vi.spyOn(repository, "decidePlanningRun");
  const user = userEvent.setup();
  setup(repository);
  await openPlanningHistory();
  await screen.findByRole("button", { name: "确认并应用" });
  const input = screen.getByRole("textbox", { name: "告诉旅程总管" });
  expect(input).toBeEnabled();
  await user.type(input, "为什么这样安排？{Enter}");
  await screen.findByText("上午保留人文游览，午间留出休息，避免连续赶路。");
  expect(screen.queryByRole("button", { name: "确认并应用" })).not.toBeInTheDocument();
  expect(create).toHaveBeenCalledTimes(1);
  expect(apply).not.toHaveBeenCalled();
  expect(input).toBeEnabled();
  expect(input).toHaveValue("");
});

it("restores an answer on reopen and shows specific reasons on proposal cards", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  const proposal = await repository.getPlanRevision();
  proposal.differenceSummary.decision_summary = { status: "validated", entries: [] };
  proposal.reason = "为满足人文偏好，上午保留博物馆，午间留出休息时间。";
  if (proposal.activities[0]) proposal.activities[0].reason = "这项游览对应你对历史的兴趣。";
  vi.spyOn(repository, "getPlanRevision").mockResolvedValue(proposal);
  const list = vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([{ ...pending, status: "awaiting_confirmation" }]);
  const view = setup(repository);
  await openPlanningHistory();
  await screen.findByText(proposal.reason);
  if (proposal.activities[0]) expect(screen.getByText("这项游览对应你对历史的兴趣。")).toBeVisible();
  view.unmount();
  list.mockResolvedValue([{ ...pending, status: "answered", responseText: "正式行程仍然保留原有安排。" }]);
  setup(repository);
  await openPlanningHistory();
  await screen.findByText("正式行程仍然保留原有安排。");
  expect(screen.queryByRole("button", { name: "确认并应用" })).not.toBeInTheDocument();
});

it("hides unsupported walking claims while keeping a pending revision actionable", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  const proposal = await repository.getPlanRevision();
  proposal.reason = "已减少步行";
  if (proposal.activities[0]) proposal.activities[0].reason = "已减少步行";
  proposal.differenceSummary.decision_summary = { status: "invalid", entries: [], error_codes: ["decision_explanation_unsupported"] };
  vi.spyOn(repository, "getPlanRevision").mockResolvedValue(proposal);
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([{ ...pending, status: "awaiting_confirmation" }]);
  setup(repository);
  await openPlanningHistory();
  expect(await screen.findByText("调整原因暂未通过核验")).toBeInTheDocument();
  expect(screen.getByText("AI生成的候选调整")).toBeInTheDocument();
  expect(screen.queryByText("已减少步行")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "暂不采用" })).toBeEnabled();
  // The existing empty-initial-plan guard is independent of Ledger status.
  expect(screen.getByRole("button", { name: "确认并应用" })).toBeDisabled();
});

it("removes a rejected proposal from the active plan and keeps new planning available", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([{ ...pending, status: "awaiting_confirmation" }]);
  const original = await repository.getPlanRevision();
  const reject = vi.spyOn(repository, "rejectPlanRevision").mockResolvedValue({ ...original, status: "rejected", rejectionReasonCode: "too_rushed" });
  const user = userEvent.setup();
  setup(repository);
  await openPlanningHistory();
  await user.click(await screen.findByRole("button", { name: "暂不采用" }));
  expect(screen.getByText("为什么不采用这个方案？")).toBeVisible();
  await user.selectOptions(screen.getByRole("combobox", { name: "拒绝原因" }), "too_rushed");
  await user.click(screen.getByRole("button", { name: "确认拒绝" }));
  await screen.findByText(/已暂不采用这份方案/);
  expect(screen.queryByText("为什么这样安排")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "确认并应用" })).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "告诉旅程总管" })).toBeEnabled();
  expect(reject).toHaveBeenCalledWith(original.id, { reasonCode: "too_rushed", reasonText: "" });
});

it("retries a failed planning run with the exact request and creates an independent run", async () => {
  const repository = new LocalTripPlanningRepository(localStorage);
  const failed = { ...pending, status: "failed" as const, errorCode: "planner_invalid_output", userRequest: "请再调整一次 2026-10-20 当天的行程" };
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([failed]);
  vi.spyOn(repository, "getPlanningRun").mockResolvedValue(failed);
  const create = vi.spyOn(repository, "createPlanningRun").mockResolvedValue({ ...failed, id: "independent-run", status: "queued" });
  const reject = vi.spyOn(repository, "rejectPlanRevision");
  setup(repository);
  await openPlanningHistory();
  await userEvent.click(await screen.findByRole("button", { name: "重试本次需求" }));
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(create.mock.calls[0][1]).toBe(failed.userRequest);
  expect(reject).not.toHaveBeenCalled();
});

it("starts an independent failed-run retry even when an assistant session is present", async () => {
  const session: AssistantSession = { id: "session", trip_id: "demo", messages: [], pending_action: null, latest_run_id: "saved-run" };
  const send = vi.fn();
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session), sendAssistantMessage: send });
  const failed = { ...pending, runType: "replan" as const, status: "failed" as const, errorCode: "planner_invalid_output", userRequest: "请再调整一次" };
  vi.spyOn(repository, "getPlanningRun").mockResolvedValue(failed);
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([failed]);
  const create = vi.spyOn(repository, "createPlanningRun").mockResolvedValue({ ...failed, id: "new-run", status: "queued" });
  setup(repository);
  await openPlanningHistory();
  const retryButton = await screen.findByRole("button", { name: "重试本次需求" });
  await waitFor(() => expect(retryButton).toBeEnabled());
  await userEvent.click(retryButton);
  await waitFor(() => expect(create).toHaveBeenCalledOnce());
  expect(create.mock.calls[0][0]).toBe(failed.tripId);
  expect(create.mock.calls[0][1]).toBe(failed.userRequest);
  expect(create).toHaveBeenCalledWith(failed.tripId, failed.userRequest, expect.objectContaining({ runType: "replan" }));
  expect(send).not.toHaveBeenCalled();
});


it("clears pre-trip history, preview and draft, then sends with the new session", async () => {
  const session: AssistantSession = { id: "old-home", trip_id: null, latest_run_id: null,
    messages: [{ id: "old-turn", user: "先去成都", assistant: "成都旧回复" }],
    pending_action: { id: "old-action", tool: "create_trip", title: "成都旅行", city: { name: "成都" }, start_date: "2027-05-01", end_date: "2027-05-02", total_budget_fen: 10000, daily_budget_fen: 5000, preferences: "", summary: "成都创建预览" } };
  const fresh: AssistantSession = { id: "new-home", trip_id: null, messages: [], pending_action: null, latest_run_id: null };
  const reset = vi.fn().mockResolvedValue(fresh);
  const send = vi.fn().mockResolvedValue({ ...fresh, messages: [{ id: "new-turn", user: "换个城市", assistant: "聊聊新的目的地" }] });
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session), resetAssistantSession: reset, sendAssistantMessage: send });
  const props = { open: true, days: [], candidates: [], repository, onClose: () => undefined, onAccepted: async () => undefined };
  const view = render(<AiPlannerPanel {...props} />);
  expect(await screen.findByText("成都旧回复")).toBeInTheDocument();
  await userEvent.type(screen.getByRole("textbox", { name: "告诉旅程总管" }), "未发送草稿");
  await userEvent.click(screen.getByRole("button", { name: "清除对话" }));
  await waitFor(() => expect(screen.queryByText("成都旧回复")).not.toBeInTheDocument());
  expect(screen.queryByText("成都创建预览")).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "告诉旅程总管" })).toHaveValue("");
  expect(reset).toHaveBeenCalledWith("old-home");
  await userEvent.type(screen.getByRole("textbox", { name: "告诉旅程总管" }), "换个城市");
  await userEvent.click(screen.getByRole("button", { name: "发送需求" }));
  expect(await screen.findByText("聊聊新的目的地")).toBeInTheDocument();
  expect(send).toHaveBeenCalledWith("new-home", "换个城市", expect.any(String), undefined, undefined);
  view.unmount();
  repository.getAssistantSession.mockResolvedValue(fresh);
  render(<AiPlannerPanel {...props} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "发送需求" })).not.toHaveTextContent("正在处理"));
  expect(screen.queryByText("成都旧回复")).not.toBeInTheDocument();
});

it("preserves the conversation and draft if clearing fails", async () => {
  const session: AssistantSession = { id: "home", trip_id: null, messages: [{ id: "one", user: "旧问题", assistant: "旧回复" }], pending_action: null, latest_run_id: null };
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session), resetAssistantSession: vi.fn().mockRejectedValue(new Error("清除失败")) });
  render(<AiPlannerPanel open days={[]} candidates={[]} repository={repository} onClose={() => undefined} onAccepted={async () => undefined} />);
  await screen.findByText("旧回复");
  await userEvent.type(screen.getByRole("textbox", { name: "告诉旅程总管" }), "草稿");
  await userEvent.click(screen.getByRole("button", { name: "清除对话" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("清除失败");
  expect(screen.getByText("旧回复")).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "告诉旅程总管" })).toHaveValue("草稿");
});

it("offers no clearing button for a saved trip", async () => {
  const session: AssistantSession = { id: "saved", trip_id: "demo", messages: [{ id: "one", user: "保存问题", assistant: "旅行历史" }], pending_action: null, latest_run_id: null };
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session), resetAssistantSession: vi.fn() });
  setup(repository);
  await screen.findByText("旅行历史");
  expect(screen.queryByRole("button", { name: "清除对话" })).not.toBeInTheDocument();
});

it("restores the session's current candidate after navigating to the created trip", async () => {
  const session: AssistantSession = { id: "created", trip_id: "demo", messages: [], pending_action: null, latest_run_id: "saved-run" };
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session) });
  const getRun = vi.spyOn(repository, "getPlanningRun").mockResolvedValue({ ...pending, status: "awaiting_confirmation" });
  const getRevision = vi.spyOn(repository, "getPlanRevision").mockResolvedValue({
    id: "saved-revision", planningRunId: "saved-run", reason: "现有候选", activities: [{
      candidateId: "activity-proposal", dayDate: "2026-10-09", placeCandidateId: "place",
      plannedStartTime: "09:00", durationMinutes: 60, estimatedCostFen: 0,
      transportModeToHere: "walk", reason: "proposal", locked: false,
    }],
    differenceSummary: {}, validationResult: { valid: true }, sourceIds: [], status: "pending",
  });
  const listRuns = vi.spyOn(repository, "listPlanningRuns");
  const context = vi.spyOn(repository, "getPlanningContext");
  setup(repository);
  expect(await screen.findByText("候选方案")).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "确认并应用" })).toBeEnabled());
  expect(getRun).toHaveBeenCalledWith("saved-run");
  expect(getRevision).toHaveBeenCalledWith("saved-run");
  expect(listRuns).not.toHaveBeenCalled();
  expect(context).not.toHaveBeenCalled();
});

it("does not restore a saved run belonging to a different trip", async () => {
  const session: AssistantSession = { id: "created", trip_id: "demo", messages: [], pending_action: null, latest_run_id: "wrong-run" };
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session) });
  vi.spyOn(repository, "getPlanningRun").mockResolvedValue({ ...pending, tripId: "other-trip" });
  const getRevision = vi.spyOn(repository, "getPlanRevision");
  setup(repository);
  expect(await screen.findByRole("alert")).toHaveTextContent("规划任务不属于当前旅行");
  expect(screen.queryByText("候选方案")).not.toBeInTheDocument();
  expect(getRevision).not.toHaveBeenCalled();
});

it("restores planning progress without opening developer monitoring", async () => {
  const session: AssistantSession = { id: "created", trip_id: "demo", messages: [], pending_action: null, latest_run_id: "saved-run" };
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session) });
  vi.spyOn(repository, "getPlanningRun").mockResolvedValue({ ...pending, status: "researching",
    progress: { stage: "search", message: "正在搜索网页资料…", updated_at: new Date().toISOString() } });
  setup(repository);
  expect(await screen.findByText("正在搜索网页资料…")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("本阶段已等待");
});

it("recovers a unique pending proposal after an old Companion reply cleared the session pointer", async () => {
  const session: AssistantSession = { id: "created", trip_id: "demo", latest_run_id: null, pending_action: null,
    messages: [{ id: "confirmed", user: "确认执行", assistant: "旅行已创建，正在准备候选行程。", run_id: null }] };
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session) });
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([{ ...pending, status: "awaiting_confirmation" }]);
  vi.spyOn(repository, "getPlanningRun").mockResolvedValue({ ...pending, status: "awaiting_confirmation" });
  vi.spyOn(repository, "getPlanRevision").mockResolvedValue({ id: "revision", planningRunId: "saved-run", status: "pending",
    reason: "保存的候选", activities: [{ candidateId: "fixture", dayDate: "2026-10-11", placeCandidateId: "place",
      plannedStartTime: "10:00", durationMinutes: 60, estimatedCostFen: 0, transportModeToHere: "walk", reason: "保存说明", locked: false }],
    differenceSummary: {}, validationResult: { valid: true }, sourceIds: [] });
  setup(repository);
  await waitFor(() => expect(screen.getByRole("button", { name: "确认并应用" })).toBeEnabled());
});

it("does not silently choose between multiple pending proposals", async () => {
  const session: AssistantSession = { id: "created", trip_id: "demo", latest_run_id: null, pending_action: null,
    messages: [{ id: "confirmed", user: "确认执行", assistant: "旅行已创建，正在准备候选行程。", run_id: null }] };
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), { getAssistantSession: vi.fn().mockResolvedValue(session) });
  vi.spyOn(repository, "listPlanningRuns").mockResolvedValue([{ ...pending, status: "awaiting_confirmation" }, { ...pending, id: "other", status: "awaiting_confirmation" }]);
  const getRevision = vi.spyOn(repository, "getPlanRevision");
  setup(repository);
  expect(await screen.findByRole("alert")).toHaveTextContent("多份待处理方案");
  expect(getRevision).not.toHaveBeenCalled();
});

it("keeps the candidate visible while answering a Companion explanation", async () => {
  const session: AssistantSession = { id: "created", trip_id: "demo", messages: [], pending_action: null, latest_run_id: "saved-run" };
  const answer = { response_text: "生成时保存的安排说明", goal_type: "explanation" as const, status: "completed" as const,
    suggestions: [], resolved_suggestion_refs: [], runtime_trace: [], explanation: {
      explanation_type: "saved_plan_notes", reasons: ["文化兴趣"], based_on_prior_decision: false,
      source_decision_ref: "revision:fixture", fact_freshness_warning: "尚未验证事实依据" } };
  const repository = Object.assign(new LocalTripPlanningRepository(localStorage), {
    getAssistantSession: vi.fn().mockResolvedValue(session),
    sendAssistantMessage: vi.fn().mockResolvedValue({ ...session, messages: [{ id: "question", user: "为什么会这样安排？",
      assistant: answer.response_text, companion_result: answer }] }),
  });
  vi.spyOn(repository, "getPlanningRun").mockResolvedValue({ ...pending, status: "awaiting_confirmation" });
  vi.spyOn(repository, "getPlanRevision").mockResolvedValue({ id: "revision", planningRunId: "saved-run", status: "pending",
    reason: "保存的候选", activities: [{ candidateId: "fixture", dayDate: "2026-10-11", placeCandidateId: "place",
      plannedStartTime: "10:00", durationMinutes: 60, estimatedCostFen: 0, transportModeToHere: "walk", reason: "保存说明", locked: false }],
    differenceSummary: {}, validationResult: { valid: true }, sourceIds: [] });
  setup(repository);
  await waitFor(() => expect(screen.getByRole("button", { name: "确认并应用" })).toBeEnabled());
  const input = screen.getByRole("textbox", { name: "告诉旅程总管" });
  fireEvent.change(input, { target: { value: "为什么会这样安排？" } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(await screen.findByText(answer.response_text)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "确认并应用" })).toBeEnabled());
  expect(screen.getByText("候选方案")).toBeInTheDocument();
  await userEvent.click(screen.getByText("回答依据"));
  expect(screen.getByText("对应方案：fixture")).toBeInTheDocument();
});
