import { describe, expect, it } from "vitest";
import { getExecutionPresentation } from "./executionPresentation";
import { getRecoveryLifecycle } from "./executionPresentation";

describe("getExecutionPresentation", () => {
  it.each([["normal", "行程正常"], ["eta_delayed", "预计到达有所延迟"], ["disruption", "当前计划已受到影响"], ["unknown", "执行状态暂不可确认"]] as const)("maps %s without changing backend risk", (risk, label) => {
    expect(getExecutionPresentation(risk).label).toBe(label);
  });
});

it("keeps rejected recovery distinct from a resolved disruption", () => {
  expect(getRecoveryLifecycle({ id: "run", status: "rejected", disruptionEventId: "event", baseTripVersion: 1 }, false).message).toContain("风险仍然存在");
});
