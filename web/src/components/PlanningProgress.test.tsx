import { act, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { PlanningProgress } from "./PlanningProgress";
import type { PlanningRun } from "../domain/types";

it("shows elapsed waiting and stale heartbeat without inventing a new stage", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-09-10T00:00:00Z"));
  const run: PlanningRun = { id: "one", tripId: "trip", runType: "initial_plan", status: "researching", userRequest: "规划", tokenUsage: 0,
    progress: { stage: "research_model", message: "已取得8条资料，等待模型返回", updated_at: new Date().toISOString() }, heartbeatAt: new Date().toISOString() };
  const { rerender, unmount } = render(<PlanningProgress run={run} />);
  expect(screen.getByRole("status")).toHaveTextContent("任务心跳正常");
  act(() => vi.advanceTimersByTime(120000));
  expect(screen.getByRole("status")).toHaveTextContent("本阶段已等待 120 秒");
  expect(screen.getByRole("status")).toHaveTextContent("执行可能中断");
  expect(screen.getByRole("status")).toHaveTextContent("已取得8条资料，等待模型返回");
  rerender(<PlanningProgress run={{ ...run, heartbeatAt: new Date().toISOString() }} />);
  expect(screen.getByRole("status")).toHaveTextContent("任务心跳正常");
  expect(screen.getByRole("status")).toHaveTextContent("心跳正常不代表模型已完成");
  unmount();
  vi.useRealTimers();
});
