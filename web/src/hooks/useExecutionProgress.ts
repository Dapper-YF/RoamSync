import { useCallback, useEffect, useRef, useState } from "react";
import type { ExecutionProgress, TripPlanningRepository } from "../domain/types";

export interface ExecutionProgressQuery {
  data: ExecutionProgress | null;
  error: Error | null;
  isInitialLoading: boolean;
  isRefreshing: boolean;
  isStale: boolean;
  lastUpdatedAt: string | null;
  refresh: () => Promise<void>;
}

const ACTIVE_RUNS = new Set(["queued", "researching", "awaiting_clarification", "planning", "validating", "awaiting_confirmation"]);
const POLL_MS = 15_000;

/** One server-state owner for execution UI.  Old responses are fenced locally. */
export function useExecutionProgress(repository: TripPlanningRepository, tripId: string | null | undefined): ExecutionProgressQuery {
  const [data, setData] = useState<ExecutionProgress | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isInitialLoading, setInitialLoading] = useState(Boolean(tripId));
  const [isRefreshing, setRefreshing] = useState(false);
  const generation = useRef(0);
  const currentTrip = useRef<string | null | undefined>(tripId);

  const refresh = useCallback(async () => {
    if (!tripId) return;
    const requestGeneration = ++generation.current;
    const isInitial = data === null;
    if (isInitial) setInitialLoading(true); else setRefreshing(true);
    try {
      const next = await repository.getExecutionProgress(tripId);
      if (generation.current !== requestGeneration || currentTrip.current !== tripId) return;
      setData(next); setError(null);
    } catch (cause) {
      if (generation.current !== requestGeneration || currentTrip.current !== tripId) return;
      setError(cause instanceof Error ? cause : new Error("执行状态更新失败"));
    } finally {
      if (generation.current === requestGeneration && currentTrip.current === tripId) {
        setInitialLoading(false); setRefreshing(false);
      }
    }
  }, [data, repository, tripId]);

  useEffect(() => {
    currentTrip.current = tripId;
    generation.current += 1;
    setData(null); setError(null); setInitialLoading(Boolean(tripId)); setRefreshing(false);
    if (tripId) void refresh();
  // Refresh is intentionally re-created when data changes; this reset effect
  // owns only the identity boundary, not polling.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repository, tripId]);

  useEffect(() => {
    if (!tripId || !data) return;
    const shouldPoll = data.navigationSession?.status === "active" || data.navigationSession?.status === "rerouting" || Boolean(data.activeRecoveryRun && ACTIVE_RUNS.has(data.activeRecoveryRun.status));
    if (!shouldPoll) return;
    const onVisible = () => { if (!document.hidden) void refresh(); };
    document.addEventListener("visibilitychange", onVisible);
    const timer = window.setInterval(() => { if (!document.hidden) void refresh(); }, POLL_MS);
    return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", onVisible); };
  }, [data, refresh, tripId]);

  return { data, error, isInitialLoading, isRefreshing, isStale: Boolean(error && data), lastUpdatedAt: data?.generatedAt ?? null, refresh };
}
