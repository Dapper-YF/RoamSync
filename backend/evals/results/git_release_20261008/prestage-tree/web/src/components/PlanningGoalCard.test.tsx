import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlanningGoalCard } from "./PlanningGoalCard";
import type { PlanRevision } from "../domain/types";

const revision = {
  id: "revision-1",
  planningRunId: "run-1",
  reason: "测试目标检查结果",
  activities: [],
  differenceSummary: {},
  validationResult: { valid: true },
  sourceIds: [],
  status: "pending",
  planningGoals: {
    targetDays: ["2026-10-20"],
    hardGoals: { endBefore: "18:00", maxWalkingMinutes: 50 },
    softGoals: { pace: "relaxed", minimizeWalking: true, preserveExisting: true },
  },
  goalSatisfaction: {
    results: [
      { goal: "end_before", type: "hard", status: "satisfied", evidence: { candidate_end: "17:40", required_end_before: "18:00" } },
      { goal: "max_walking_minutes", type: "hard", status: "unsatisfied", evidence: { candidate_walking_minutes: 64, limit_minutes: 50 } },
      { goal: "pace_relaxed", type: "soft", status: "partially_satisfied", evidence: { activity_count_before: 5, activity_count_after: 4 } },
    ],
  },
} satisfies PlanRevision;

describe("PlanningGoalCard", () => {
  it("renders structured goals and satisfied, unsatisfied, and partial results", () => {
    render(<PlanningGoalCard revision={revision} />);

    expect(screen.getByRole("region", { name: "本次规划目标与方案检查结果" })).toBeVisible();
    expect(screen.getByText("18:00 前结束")).toBeVisible();
    expect(screen.getByText(/结束时间：17:40/)).toBeVisible();
    expect(screen.getByText(/步行：64 分钟/)).toHaveClass("goal-unsatisfied");
    expect(screen.getByText(/轻松节奏：活动 5 → 4 项/)).toHaveClass("goal-partially_satisfied");
  });
});
