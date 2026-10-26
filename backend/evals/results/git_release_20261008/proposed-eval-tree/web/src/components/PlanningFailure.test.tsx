import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { PlanningFailure } from "./PlanningFailure";
import type { PlanningRun } from "../domain/types";

const run: PlanningRun = { id: "failed", tripId: "trip", runType: "replan", status: "failed", userRequest: "第二天轻松一点", tokenUsage: 0 };

it("retries a timing failure without steering the user's goal toward fewer places", async () => {
  const suggestion = vi.fn();
  const retry = vi.fn();
  render(<PlanningFailure run={{ ...run, errorCode: "planner_constraints_unsatisfied", errorDetails: { validation_errors: [{ code: "route_travel_time_conflict", message: "9月10日的后续活动最早应在 14:30 开始" }] } }} disabled={false} onRetry={retry} onSuggestion={suggestion} />);
  expect(screen.getByRole("alert")).toHaveTextContent("14:30");
  await userEvent.click(screen.getByRole("button", { name: "按原需求重试" }));
  expect(suggestion).not.toHaveBeenCalled();
  expect(retry).toHaveBeenCalledOnce();
});

it("offers a retry for connection failure", async () => {
  const retry = vi.fn();
  render(<PlanningFailure run={{ ...run, errorMessage: "planner provider could not be reached" }} disabled={false} onRetry={retry} onSuggestion={vi.fn()} />);
  expect(screen.getByRole("alert")).toHaveTextContent("暂时连不上 AI 服务");
  await userEvent.click(screen.getByRole("button", { name: "重试本次需求" }));
  expect(retry).toHaveBeenCalledOnce();
});

it("explains the missing route and preserves transport preferences when suggesting changes", async () => {
  const suggestion = vi.fn();
  render(<PlanningFailure run={{ ...run, errorCode: "planner_constraints_unsatisfied", errorDetails: { validation_errors: [{ code: "route_unavailable", message: "普达措 → 松赞林寺没有可用的公共交通路线" }] } }} disabled={false} onRetry={vi.fn()} onSuggestion={suggestion} />);
  expect(screen.getByRole("alert")).toHaveTextContent("普达措 → 松赞林寺");
  expect(screen.getByRole("alert")).toHaveTextContent("旅行偏好");
  await userEvent.click(screen.getByRole("button", { name: "更换不可达的补充景点" }));
  expect(suggestion.mock.calls[0][0]).toContain("保留原有主要游览与交通偏好");
});

it("hides internal reference errors and keeps retry available", async () => {
  const retry = vi.fn();
  render(<PlanningFailure run={{ ...run, errorCode: "planner_invalid_output", errorMessage: "unverified_place_candidate_id 00000000-0000-4000-8000-000000000001" }} disabled={false} onRetry={retry} onSuggestion={vi.fn()} />);
  expect(screen.getByRole("alert")).toHaveTextContent("这次方案生成失败，我没有应用任何更改");
  expect(screen.getByRole("alert")).not.toHaveTextContent("unverified_place_candidate_id");
  expect(screen.getByRole("alert")).not.toHaveTextContent("00000000");
  await userEvent.click(screen.getByRole("button", { name: "重试本次需求" }));
  expect(retry).toHaveBeenCalledOnce();
});
