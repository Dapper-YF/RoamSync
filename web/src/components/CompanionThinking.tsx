import type { AssistantSession } from "../domain/types";
import { useEffect, useState } from "react";

type Result = NonNullable<AssistantSession["messages"][number]["companion_result"]>;

// Compatibility for persisted replies from the old diagnostic renderer.
export function companionAnswer(text: string): string {
  return text.split(/资料限制：/)[0]
    .replace(/\s*\[knowledge_[^\]]+\]/g, "")
    .replace(/^(?:资料支持：|助手的推断与建议（不是来源事实）：|基于资料的策展解读（不是来源原文或官方建议）：|可讨论的建议（尚未加入正式行程）：)\s*$/gm, "")
    .replace(/\n{3,}/g, "\n\n").trim();
}

export function CompanionThinking({ result }: { result: Result }) {
  const sources = (result.knowledge_evidence ?? []).filter((source, index, all) =>
    /^https?:\/\//i.test(source.source_reference) && all.findIndex((other) =>
      other.source_reference === source.source_reference) === index);
  const general = result.grounding_limitations?.includes("model_general_knowledge_unverified");
  const explanation = result.explanation;
  return <details className="ai-thinking">
    <summary>回答依据</summary>
    <p>{explanation?.explanation_type === "current_reconstruction" ? "这次回答结合当前行程、偏好和保存说明重新生成，不代表当时的原始推理。" : explanation?.explanation_type === "saved_plan_notes" ? "这份历史回答引用了方案生成时保存的说明。" : explanation?.explanation_type === "rationale_unavailable" ? "没有找到匹配当前方案的原始理由记录。" : general ? "这次回答基于 AI 通用知识，未进行来源或实时核验。" : sources.length ?
      "这次回答参考了以下资料；旅行建议还结合了你的问题。" : result.grounding_status === "verified_forecast" ? "天气信息来自刚刚查询的预报；回答按你关心的问题作了概括。" : "这次回答结合了你的问题和当前对话。"}</p>
    {result.grounding_status === "live_verification_required" && <p>涉及当前状态的信息需要实时核实。</p>}
    {explanation?.source_decision_ref && <p>对应方案：{explanation.source_decision_ref.replace(/^revision:/, "")}</p>}
    {explanation?.fact_freshness_warning && <p>{explanation.fact_freshness_warning}</p>}
    {sources.length > 0 && <ul>{sources.map((source) => <li key={source.source_reference}>
      <a href={source.source_reference} target="_blank" rel="noopener noreferrer">{source.source_name || "参考来源"}</a>
    </li>)}</ul>}
  </details>;
}

export function ThinkingSummary({ text, active = false }: { text: string; active?: boolean }) {
  if (!text && !active) return null;
  return <details className="ai-thinking ai-analysis" open={active || undefined}>
    <summary>{active ? "Thinking · 正在分析" : "Thinking · 分析摘要"}</summary>
    <p>{text || "正在整理相关信息…"}</p>
  </details>;
}

export function StreamingText({ text }: { text: string }) {
  const [visible, setVisible] = useState("");
  useEffect(() => {
    if (!text.startsWith(visible)) { setVisible(""); return; }
    if (visible === text) return;
    const frame = requestAnimationFrame(() => setVisible((value) =>
      text.startsWith(value) ? value + (Array.from(text.slice(value.length))[0] ?? "") : ""));
    return () => cancelAnimationFrame(frame);
  }, [text, visible]);
  // Smooth live network chunks while the request is active. Persisted replies
  // render immediately; no timer pretends a completed response is streaming.
  return <div className="ai-stream-text">{visible}</div>;
}
