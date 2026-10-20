import { useState } from "react";
export type AnswerSearch = { status: string; provider?: string; sources: { url: string; title: string; excerpt?: string }[]; images: { url: string; description: string; source_url: string; topic?: string }[] };

function safeUrl(url: string) {
  try {
    const value = new URL(url);
    return value.protocol === "https:" && !value.username && !value.password && value.hostname.includes(".") && !/^(?:localhost|127\.|10\.|192\.168\.|169\.254\.)/.test(value.hostname) && !value.hostname.endsWith(".local");
  } catch { return false; }
}
function Text({ text }: { text: string }) {
  return <>{text.split(/(\*\*[^*]+\*\*)/g).map((part, n) => part.startsWith("**") && part.endsWith("**") ? <strong key={n}>{part.slice(2, -2)}</strong> : part)}</>;
}
function SearchImage({ image }: { image: AnswerSearch["images"][number] }) {
  const [failed, setFailed] = useState(false);
  if (failed || !safeUrl(image.url) || !safeUrl(image.source_url)) return null;
  const caption = image.topic ? `${image.topic}${image.description.startsWith(image.topic + "参考图") ? "参考图" : ""}` : image.description.slice(0, 80);
  return <figure><a href={image.source_url} target="_blank" rel="noopener noreferrer"><img src={image.url} alt={image.description} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} /></a><figcaption>{caption} · <a href={image.source_url} target="_blank" rel="noopener noreferrer">查看原图</a></figcaption></figure>;
}
export function AssistantAnswer({ text, search }: { text: string; search?: AnswerSearch }) {
  const paragraphs = text.split(/\n\s*\n/);
  const usable = search?.status === "available" && search.sources.length > 0;
  return <div className="assistant-answer-content">
    {paragraphs.map((paragraph, n) => <div key={n}><p><Text text={paragraph} /></p>
      {n === 0 && usable && search.images.length > 0 && <div className="assistant-answer-images">{search.images.filter(i => !i.topic || text.includes(i.topic)).slice(0, 3).map(i => <SearchImage key={i.url} image={i} />)}</div>}
    </div>)}
    {usable && <details className="ai-thinking"><summary>参考链接</summary><ul>{search.sources.filter(s => safeUrl(s.url)).map(s => <li key={s.url}><a href={s.url} target="_blank" rel="noopener noreferrer">{s.title || "查看来源"}</a></li>)}</ul></details>}
    {search?.status === "unavailable" && <p className="travel-assistant-status">这次联网搜索暂不可用，可以稍后重试。</p>}
  </div>;
}
