import type { AssistantSession } from "../domain/types";
import { useEffect, useRef, useState } from "react";
import { createStreamBuffer } from "../data/streamBuffer";

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
  const explanation = result.explanation;
  if (!sources.length && !explanation?.fact_freshness_warning) return null;
  return <details className="ai-thinking">
    <summary>{sources.length ? "参考资料" : "相关说明"}</summary>
    {explanation?.fact_freshness_warning && <p>{explanation.fact_freshness_warning}</p>}
    {sources.length > 0 && <ul>{sources.map((source) => <li key={source.source_reference}>
      <a href={source.source_reference} target="_blank" rel="noopener noreferrer">{source.source_name || "参考来源"}</a>
    </li>)}</ul>}
  </details>;
}

export function ThinkingSummary({ text, active = false }: { text: string; active?: boolean }) {
  if (!text && !active) return null;
  return <details className="ai-thinking ai-analysis" open={active || undefined}>
    <summary>{active ? "思考中…" : "思考摘要"}</summary>
    <p>{text || "正在整理相关信息…"}</p>
  </details>;
}

export function StreamingText({ text }: { text: string }) {
  const [visible, setVisible] = useState("");
  const received = useRef("");
  const buffer = useRef<ReturnType<typeof createStreamBuffer> | null>(null);
  if (!buffer.current) buffer.current = createStreamBuffer(delta => setVisible(value => value + delta));
  useEffect(() => {
    if (!text.startsWith(received.current)) { buffer.current!.reset(); received.current = ""; setVisible(""); }
    buffer.current!.push(text.slice(received.current.length));
    received.current = text;
  }, [text]);
  useEffect(() => () => buffer.current?.reset(), []);
  // Smooth live network chunks while the request is active. Persisted replies
  // render immediately; no timer pretends a completed response is streaming.
  return <div className="ai-stream-text">{visible}</div>;
}
