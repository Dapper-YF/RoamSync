import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiRequestError } from "../data/apiTripPlanningRepository";
import type { TripPlanningRepository } from "../domain/types";
import type { ExecutionProgressQuery } from "../hooks/useExecutionProgress";
import { RecoveryPanel } from "./RecoveryPanel";

function query(overrides: Partial<ExecutionProgressQuery> = {}): ExecutionProgressQuery {
  return {
    data: { tripId: "trip", itineraryVersion: 7, execution: { tripId: "trip", status: "in_progress", currentDate: "2026-09-05", scheduleDelayMinutes: 0, remainingActivityCount: 2, remainingEstimatedCostFen: 0, activities: [], events: [] }, navigationSession: null, currentActivityName: null, navigationTargetName: null, riskLevel: "disruption", minimumDownstreamSlackMinutes: -8, firstImpactedActivityId: null, activeDisruption: { id: "event", eventType: "itinerary_infeasible", impactedIdentity: "博物馆预约", impactSnapshot: {}, detectedAt: "2026-09-05T14:00:00Z", lastSeenAt: "2026-09-05T14:02:00Z", itineraryVersion: 7 }, activeRecoveryRun: { id: "run", status: "awaiting_confirmation", disruptionEventId: "event", baseTripVersion: 7 }, recoveryRevision: { id: "revision", status: "pending", reason: "缩短停留以保留预约", differenceSummary: { candidate_activity_count: 1, planned_budget_delta_fen: 1200 }, proposedSnapshot: { explanation: "缩短咖啡店停留时间，保留后续预约。", activities: [{ candidateId: "candidate", dayDate: "2026-09-05", placeCandidateId: "place", placeName: "咖啡店", plannedStartTime: "14:00", durationMinutes: 25, estimatedCostFen: 1200, transportModeToHere: "walk", reason: "压缩停留", locked: false, replacesActivityId: "activity" }] }, changeSummary: { adjustedActivities: [{ activityId: "activity", name: "咖啡店", beforeStartTime: "14:00", afterStartTime: "14:00", beforeDurationMinutes: 45, afterDurationMinutes: 25 }] } }, generatedAt: "2026-09-05T14:02:00Z" }, error: null, isInitialLoading: false, isRefreshing: false, isStale: false, lastUpdatedAt: null, refresh: vi.fn().mockResolvedValue(undefined), ...overrides,
  };
}
function repository(accept = vi.fn().mockResolvedValue({}), reject = vi.fn().mockResolvedValue({})) { return { acceptPlanRevision: accept, rejectPlanRevision: reject } as unknown as TripPlanningRepository; }

describe("RecoveryPanel", () => {
  it("renders persisted facts before the explanation and exposes one candidate decision", () => {
    render(<RecoveryPanel query={query()} repository={repository()} onAccepted={vi.fn().mockResolvedValue(undefined)} />);
    expect(screen.getByText("候选安排")).toBeInTheDocument(); expect(screen.getByText("1 项")).toBeInTheDocument(); expect(screen.getByText("+¥12.00")).toBeInTheDocument();
    expect(screen.getByText("14:00 · 45 分钟 → 14:00 · 25 分钟")).toBeInTheDocument(); expect(screen.getByText("调整原因暂未通过核验")).toBeInTheDocument();
    expect(screen.queryByText("缩短咖啡店停留时间，保留后续预约。")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "采用方案" })).toBeInTheDocument(); expect(screen.getByRole("button", { name: "拒绝方案" })).toBeInTheDocument();
  });
  it("does not invent unsupported recovery metrics", () => {
    const candidate = query(); candidate.data!.recoveryRevision!.differenceSummary = {};
    render(<RecoveryPanel query={candidate} repository={repository()} onAccepted={vi.fn().mockResolvedValue(undefined)} />);
    expect(screen.queryByText("预计追回")).not.toBeInTheDocument(); expect(screen.queryByText("调整后最小 Slack")).not.toBeInTheDocument(); expect(screen.queryByText("计划费用变化")).not.toBeInTheDocument();
  });
  it("accepts only after lightweight confirmation, then refreshes formal and execution state", async () => {
    const accept = vi.fn().mockResolvedValue({}); const accepted = vi.fn().mockResolvedValue(undefined); const candidate = query();
    render(<RecoveryPanel query={candidate} repository={repository(accept)} onAccepted={accepted} />);
    fireEvent.click(screen.getByRole("button", { name: "采用方案" })); fireEvent.click(screen.getByRole("button", { name: "确认应用" }));
    await waitFor(() => expect(accept).toHaveBeenCalledWith("revision")); expect(accepted).toHaveBeenCalledTimes(1); expect(candidate.refresh).toHaveBeenCalledTimes(1);
  });
  it("rejects without refreshing formal itinerary and keeps the disruption decision server-owned", async () => {
    const reject = vi.fn().mockResolvedValue({}); const accepted = vi.fn(); const candidate = query();
    render(<RecoveryPanel query={candidate} repository={repository(undefined, reject)} onAccepted={accepted} />);
    fireEvent.click(screen.getByRole("button", { name: "拒绝方案" }));
    await waitFor(() => expect(reject).toHaveBeenCalledWith("revision")); expect(accepted).not.toHaveBeenCalled(); expect(candidate.refresh).toHaveBeenCalledTimes(1);
  });
  it("maps a version conflict to stale-candidate guidance and refreshes reads", async () => {
    const candidate = query(); const accept = vi.fn().mockRejectedValue(new ApiRequestError(409, "formal trip changed")); const accepted = vi.fn().mockResolvedValue(undefined);
    render(<RecoveryPanel query={candidate} repository={repository(accept)} onAccepted={accepted} />); fireEvent.click(screen.getByRole("button", { name: "采用方案" })); fireEvent.click(screen.getByRole("button", { name: "确认应用" }));
    expect(await screen.findByText("行程已经发生变化，该恢复方案已过期。")).toBeInTheDocument(); expect(accepted).toHaveBeenCalled(); expect(candidate.refresh).toHaveBeenCalled();
  });
  it("guards duplicate mutations and disables a stale execution projection", async () => {
    let resolve!: () => void; const accept = vi.fn(() => new Promise<void>((done) => { resolve = done; })); const candidate = query();
    const view = render(<RecoveryPanel query={candidate} repository={repository(accept)} onAccepted={vi.fn().mockResolvedValue(undefined)} />); fireEvent.click(screen.getByRole("button", { name: "采用方案" })); fireEvent.click(screen.getByRole("button", { name: "确认应用" }));
    expect(screen.getAllByRole("button", { name: "正在处理…" })[1]).toBeDisabled(); expect(accept).toHaveBeenCalledTimes(1); await act(async () => { resolve(); }); view.unmount();
    render(<RecoveryPanel query={query({ isStale: true, error: new Error("offline") })} repository={repository()} onAccepted={vi.fn().mockResolvedValue(undefined)} />); expect(screen.getByRole("button", { name: "采用方案" })).toBeDisabled(); expect(screen.getByText(/请刷新后再应用方案/)).toBeInTheDocument();
  });
  it("does not render an actionable panel once no pending server revision exists", () => {
    const candidate = query(); candidate.data!.recoveryRevision = null;
    const view = render(<RecoveryPanel query={candidate} repository={repository()} onAccepted={vi.fn().mockResolvedValue(undefined)} />); expect(view.container.firstChild).toBeNull();
  });
});
