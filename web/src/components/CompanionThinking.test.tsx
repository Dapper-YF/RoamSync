import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { companionAnswer, CompanionThinking } from "./CompanionThinking";

describe("Companion answer presentation", () => {
  it("cleans diagnostic headings and internal citations in persisted replies", () => {
    expect(companionAnswer("资料支持：\n西湖文化景观。 [knowledge_internal]\n\n助手的推断与建议（不是来源事实）：\n可以摄影。\n\n资料限制：\n- 未覆盖摄影"))
      .toBe("西湖文化景观。\n\n可以摄影。");
  });
  it("keeps answer basis collapsed until the user expands it", () => {
    render(<CompanionThinking result={{ response_text: "最终回答", goal_type: "travel_chat", status: "completed",
      suggestions: [], resolved_suggestion_refs: [], runtime_trace: ["private_node"],
      grounding_limitations: ["model_general_knowledge_unverified"] }} />);
    const toggle = screen.getByText("回答依据");
    const details = toggle.closest("details")!;
    expect(details.open).toBe(false);
    fireEvent.click(toggle);
    expect(details.open).toBe(true);
    expect(screen.getByText(/基于 AI 通用知识/)).toBeVisible();
    expect(screen.queryByText("private_node")).toBeNull();
  });
});
