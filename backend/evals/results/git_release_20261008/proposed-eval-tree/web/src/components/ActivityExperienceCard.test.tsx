import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ExecutionProgressQuery } from "../hooks/useExecutionProgress";
import type { TripPlanningRepository } from "../domain/types";
import { ActivityExperienceCard } from "./ActivityExperienceCard";

function query(status: "pending" | "arrived" | "in_progress" = "in_progress", impact: "absorbed" | "at_risk" | "infeasible" | null = null): ExecutionProgressQuery {
  return { data: { tripId: "trip", itineraryVersion: 1, navigationSession: null, currentActivityName: "故宫", navigationTargetName: "下一站", riskLevel: "unknown", minimumDownstreamSlackMinutes: null, firstImpactedActivityId: null, activeDisruption: null, activeRecoveryRun: null, recoveryRevision: null, recoveryPlanning: null, generatedAt: "2026-09-22T10:00:00Z", experienceImpact: impact ? { impactState: impact, minimumDownstreamSlackMinutes: 12 } : null, currentActivityExperience: { activityExecutionId: "execution-activity", activityId: "activity", plannedDurationMinutes: 120, elapsedExperienceMinutes: 52, totalExtensionMinutes: 30, projectedEndAt: "2026-09-22T13:08:00Z" }, execution: { id: "execution", tripId: "trip", status: "in_progress", currentDate: "2026-09-22", currentActivityId: "activity", scheduleDelayMinutes: 0, remainingActivityCount: 2, remainingEstimatedCostFen: 0, activities: [{ id: "execution-activity", activityId: "activity", dayPlanId: "day", dayDate: "2026-09-22", name: "故宫", scheduledTime: "10:00", estimatedCostFen: 0, status, delayMinutes: 0 }], events: [] } }, error: null, isInitialLoading: false, isRefreshing: false, isStale: false, lastUpdatedAt: null, refresh: vi.fn().mockResolvedValue(undefined) };
}

function repository(): TripPlanningRepository {
  return { extendStay: vi.fn().mockResolvedValue(undefined), leaveEarly: vi.fn().mockResolvedValue(undefined), applyTripExecutionAction: vi.fn().mockResolvedValue({}), } as unknown as TripPlanningRepository;
}

describe("ActivityExperienceCard", () => {
  it("records arrival before offering the activity start command", () => {
    const repo = repository(); render(<ActivityExperienceCard query={query("pending")} repository={repo} />);
    fireEvent.click(screen.getByRole("button", { name: "我已到达" }));
    expect(repo.applyTripExecutionAction).toHaveBeenCalledWith("execution", "arrive", "activity");
  });
  it("shows arrived state and starts the existing activity execution action", async () => {
    const repo = repository(); render(<ActivityExperienceCard query={query("arrived")} repository={repo} />);
    expect(screen.getByText("已到达")).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "开始游玩" }));
    expect(repo.applyTripExecutionAction).toHaveBeenCalledWith("execution", "start_activity", "activity");
  });
  it("renders persisted experience facts and sends distinct extend actions", async () => {
    const repo = repository(); render(<ActivityExperienceCard query={query()} repository={repo} />);
    expect(screen.getByText("120 分钟")).toBeInTheDocument(); expect(screen.getByText("52 分钟")).toBeInTheDocument(); expect(screen.getByText("30 分钟")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /再待 30 分钟/ })); await waitFor(() => expect(vi.mocked(repo.extendStay)).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: /再待 30 分钟/ })); await waitFor(() => expect(vi.mocked(repo.extendStay)).toHaveBeenCalledTimes(2));
    const calls = vi.mocked(repo.extendStay).mock.calls; expect(calls[0][1]).toBe(30); expect(calls[0][2]).not.toBe(calls[1][2]);
  });
  it("explains absorbed, at-risk and infeasible states without inventing a new plan", () => {
    const view = render(<ActivityExperienceCard query={query("in_progress", "absorbed")} repository={repository()} />); expect(screen.getByText(/现有时间余量吸收/)).toBeInTheDocument();
    view.rerender(<ActivityExperienceCard query={query("in_progress", "at_risk")} repository={repository()} />); expect(screen.getByText(/最小余量：12 分钟/)).toBeInTheDocument();
    view.rerender(<ActivityExperienceCard query={query("in_progress", "infeasible")} repository={repository()} />); expect(screen.getByText(/影响后续安排/)).toBeInTheDocument();
  });
  it("records leave early through the server-owned command", () => {
    const repo = repository(); render(<ActivityExperienceCard query={query()} repository={repo} />); fireEvent.click(screen.getByRole("button", { name: /结束游玩/ })); expect(repo.leaveEarly).toHaveBeenCalledWith("execution-activity", expect.any(String));
  });
});
