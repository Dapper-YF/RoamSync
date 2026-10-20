import type { AssistantSession } from "../domain/types";
import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, LoaderCircle } from "lucide-react";
import { createStreamBuffer } from "../data/streamBuffer";
import "./CompanionThinking.css";

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
  const [expanded, setExpanded] = useState(active);
  const contentId = useId();
  // Collapse when the answer starts, even if the summary was opened while live.
  // Once complete, the user can reopen it independently of later text updates.
  useEffect(() => { setExpanded(active); }, [active]);
  if (!text && !active) return null;
  return <section className="thinking-summary" aria-label="思考摘要" data-active={active}>
    <button type="button" className="thinking-summary-toggle" aria-expanded={expanded}
      aria-controls={contentId} onClick={() => setExpanded(value => !value)}>
      {active && <LoaderCircle size={14} className="thinking-summary-spinner" aria-hidden="true" />}
      <span>{active ? "思考中…" : "思考摘要"}</span>
      <ChevronDown size={14} className="thinking-summary-chevron" aria-hidden="true" />
    </button>
    <div id={contentId} className="thinking-summary-content" hidden={!expanded}>
      <p>{text || "正在整理相关信息…"}</p>
    </div>
  </section>;
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
