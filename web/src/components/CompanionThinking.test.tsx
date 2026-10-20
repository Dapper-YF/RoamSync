import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { companionAnswer, CompanionThinking, ThinkingSummary } from "./CompanionThinking";

describe("Companion answer presentation", () => {
  it("collapses the separate summary when the answer starts and lets the user reopen it", () => {
    const { rerender } = render(<><ThinkingSummary text="先比较步行距离与游玩节奏。" active /><p>正文位置</p></>);
    expect(screen.getByRole("button", { name: "思考中…" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("先比较步行距离与游玩节奏。")).toBeVisible();
    rerender(<><ThinkingSummary text="先比较步行距离与游玩节奏。" /><p>推荐先去人民公园。</p></>);
    const toggle = screen.getByRole("button", { name: "思考摘要" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("先比较步行距离与游玩节奏。")).not.toBeVisible();
    expect(screen.getByText("推荐先去人民公园。")).toBeVisible();
    fireEvent.click(toggle);
    expect(screen.getByText("先比较步行距离与游玩节奏。")).toBeVisible();
    rerender(<><ThinkingSummary text="先比较步行距离与游玩节奏，再考虑兴趣。" /><p>推荐先去人民公园。</p></>);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });
  it("keeps saved summaries collapsed and omits an absent summary", () => {
    const { rerender } = render(<ThinkingSummary text="保存的摘要" />);
    expect(screen.getByRole("button", { name: "思考摘要" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("保存的摘要")).not.toBeVisible();
    rerender(<ThinkingSummary text="" />);
    expect(screen.queryByRole("region", { name: "思考摘要" })).toBeNull();
  });
  it("cleans diagnostic headings and internal citations in persisted replies", () => {
    expect(companionAnswer("资料支持：\n西湖文化景观。 [knowledge_internal]\n\n助手的推断与建议（不是来源事实）：\n可以摄影。\n\n资料限制：\n- 未覆盖摄影"))
      .toBe("西湖文化景观。\n\n可以摄影。");
  });
  it("does not expose internal general-knowledge metadata or invent thinking", () => {
    render(<CompanionThinking result={{ response_text: "最终回答", goal_type: "travel_chat", status: "completed",
      suggestions: [], resolved_suggestion_refs: [], runtime_trace: ["private_node"],
      grounding_limitations: ["model_general_knowledge_unverified"] }} />);
    expect(screen.queryByText("回答依据")).toBeNull();
    expect(screen.queryByText(/基于 AI 通用知识/)).toBeNull();
    expect(screen.queryByText("private_node")).toBeNull();
  });
  it("retains actual source links as an optional collapsed reference", () => {
    render(<CompanionThinking result={{ response_text: "回答", goal_type: "travel_chat", status: "completed", suggestions: [], resolved_suggestion_refs: [], runtime_trace: [], knowledge_evidence: [{ evidence_ref: "a", text: "文化", source_reference: "https://example.org/history", source_name: "文化资料", knowledge_type: "history_culture", scope: "stable" }] }} />);
    const toggle = screen.getByText("参考资料");
    expect(toggle.closest("details")!.open).toBe(false);
    fireEvent.click(toggle);
    expect(screen.getByRole("link", { name: "文化资料" })).toHaveAttribute("href", "https://example.org/history");
  });
});
