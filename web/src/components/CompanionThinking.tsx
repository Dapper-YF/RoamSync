import type { AssistantSession } from "../domain/types";

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
  return <details className="ai-thinking">
    <summary>Thinking · 回答说明</summary>
    <p>{general ? "这次回答基于 AI 通用知识，未进行来源或实时核验。" : sources.length ?
      "这次回答参考了以下资料；旅行建议还结合了你的问题。" : "这次回答结合了你的问题和当前对话。"}</p>
    {result.grounding_status === "live_verification_required" && <p>涉及当前状态的信息需要实时核实。</p>}
    {sources.length > 0 && <ul>{sources.map((source) => <li key={source.source_reference}>
      <a href={source.source_reference} target="_blank" rel="noopener noreferrer">{source.source_name || "参考来源"}</a>
    </li>)}</ul>}
    <p>这里展示回答依据与处理说明。</p>
  </details>;
}
