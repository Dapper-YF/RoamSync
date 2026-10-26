import { fireEvent, render, screen } from "@testing-library/react";
import { DecisionSummary } from "./DecisionSummary";
import type { PlanRevision } from "../domain/types";

const base: PlanRevision = {
  id: "revision", planningRunId: "run", reason: "调整", activities: [],
  differenceSummary: {}, validationResult: {}, sourceIds: [], status: "pending",
};

it("shows only validated remove, preserve and duration decisions in a collapsed panel", () => {
  const revision = { ...base, differenceSummary: { decision_summary: { status: "validated", entries: [
    { decision_id: "1", action_type: "remove", activity_name: "断桥", reason: "减少步行", evidence_status: "validated" },
    { decision_id: "2", action_type: "preserve", activity_name: "博物馆", reason: "保留你标记为必去的活动", evidence_status: "validated" },
    { decision_id: "3", action_type: "shorten", activity_name: "茶园", before: { duration_minutes: 90 }, after: { duration_minutes: 70 }, reason: "满足明确的时间或步行限制", evidence_status: "validated" },
    { decision_id: "4", action_type: "add", activity_name: "错误地点", reason: "未经核实", evidence_status: "invalid" },
  ] } } };
  const { container } = render(<DecisionSummary revision={revision} />);
  expect(container.querySelector("details")).not.toHaveAttribute("open");
  fireEvent.click(screen.getByText("为什么这样调整？"));
  expect(container.querySelector("details")).toHaveAttribute("open");
  expect(screen.getByText("移出 断桥")).toBeInTheDocument();
  expect(screen.getByText("保留 博物馆")).toBeInTheDocument();
  expect(screen.getByText("缩短停留 茶园")).toBeInTheDocument();
  expect(screen.getByText(/90 → 70 分钟/)).toBeInTheDocument();
  expect(screen.queryByText("错误地点")).not.toBeInTheDocument();
});

it("keeps historical revisions readable without a ledger", () => {
  render(<DecisionSummary revision={base} />);
  expect(screen.getByText("暂无结构化调整依据")).toBeInTheDocument();
});
