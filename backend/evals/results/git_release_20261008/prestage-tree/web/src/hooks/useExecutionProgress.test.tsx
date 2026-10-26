import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useExecutionProgress } from "./useExecutionProgress";
import type { ExecutionProgress, TripPlanningRepository } from "../domain/types";

const progress = (tripId: string, riskLevel: ExecutionProgress["riskLevel"] = "normal"): ExecutionProgress => ({
  tripId, itineraryVersion: 1, execution: { tripId, status: "in_progress", currentDate: "2026-09-05", scheduleDelayMinutes: 0, remainingActivityCount: 1, remainingEstimatedCostFen: 0, activities: [], events: [] },
  navigationSession: { id: `${tripId}-session`, itineraryVersion: 1, fromActivityId: "a", toActivityId: "b", plannedDepartureAt: "2026-09-05T09:00:00Z", plannedArrivalAt: "2026-09-05T09:30:00Z", status: "active", updatedAt: "2026-09-05T09:00:00Z" },
  currentActivityName: null, navigationTargetName: null, riskLevel, minimumDownstreamSlackMinutes: null,
  firstImpactedActivityId: null, activeDisruption: null, activeRecoveryRun: null, recoveryRevision: null, generatedAt: "2026-09-05T09:00:00Z",
});

function repository(getExecutionProgress: TripPlanningRepository["getExecutionProgress"]): TripPlanningRepository {
  return { getExecutionProgress } as TripPlanningRepository;
}

describe("useExecutionProgress", () => {
  it("preserves the backend unknown state", async () => {
    const adapter = repository(vi.fn().mockResolvedValue(progress("trip", "unknown")));
    const view = renderHook(() => useExecutionProgress(adapter, "trip"));
    await waitFor(() => expect(view.result.current.data?.riskLevel).toBe("unknown"));
  });

  it("keeps last successful data and marks it stale after a refresh failure", async () => {
    const load = vi.fn().mockResolvedValueOnce(progress("trip")).mockRejectedValueOnce(new Error("network down"));
    const adapter = repository(load);
    const view = renderHook(() => useExecutionProgress(adapter, "trip"));
    await waitFor(() => expect(view.result.current.data).not.toBeNull());
    await act(async () => { await view.result.current.refresh(); });
    expect(view.result.current.data?.tripId).toBe("trip");
    expect(view.result.current.isStale).toBe(true);
    expect(view.result.current.error?.message).toBe("network down");
  });

  it("fences an old response after a trip switch", async () => {
    let resolveA!: (value: ExecutionProgress) => void;
    const pendingA = new Promise<ExecutionProgress>((resolve) => { resolveA = resolve; });
    const load = vi.fn((tripId: string) => tripId === "A" ? pendingA : Promise.resolve(progress("B")));
    const adapter = repository(load);
    const view = renderHook(({ tripId }) => useExecutionProgress(adapter, tripId), { initialProps: { tripId: "A" } });
    view.rerender({ tripId: "B" });
    await waitFor(() => expect(view.result.current.data?.tripId).toBe("B"));
    await act(async () => { resolveA(progress("A")); await Promise.resolve(); });
    expect(view.result.current.data?.tripId).toBe("B");
  });

  it("does not let an older refresh overwrite a newer response for one trip", async () => {
    let resolveFirst!: (value: ExecutionProgress) => void;
    let resolveSecond!: (value: ExecutionProgress) => void;
    const first = new Promise<ExecutionProgress>((resolve) => { resolveFirst = resolve; });
    const second = new Promise<ExecutionProgress>((resolve) => { resolveSecond = resolve; });
    const load = vi.fn().mockReturnValueOnce(first).mockReturnValueOnce(second);
    const adapter = repository(load);
    const view = renderHook(() => useExecutionProgress(adapter, "trip"));
    await act(async () => { void view.result.current.refresh(); resolveSecond(progress("trip", "disruption")); await Promise.resolve(); });
    await waitFor(() => expect(view.result.current.data?.riskLevel).toBe("disruption"));
    await act(async () => { resolveFirst(progress("trip", "normal")); await Promise.resolve(); });
    expect(view.result.current.data?.riskLevel).toBe("disruption");
  });
});
