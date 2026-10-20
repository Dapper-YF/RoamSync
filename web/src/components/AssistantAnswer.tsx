import { useState } from "react";
export type AnswerSearch = { status: string; provider?: string; sources: { source_id?: string; place_id?: string; url: string; title: string; excerpt?: string; read_level?: "page_text" | "search_excerpt" | "provider_reference"; retrieved_at?: string }[]; images: { url: string; description: string; source_url: string; topic?: string; place_id?: string; usage_basis?: string; license_url?: string; license_name?: string; attribution?: string; changes?: string }[] };

function safeUrl(url: string) {
  try {
    const value = new URL(url);
    return value.protocol === "https:" && !value.username && !value.password && value.hostname.includes(".") && !/^(?:localhost|127\.|10\.|192\.168\.|169\.254\.)/.test(value.hostname) && !value.hostname.endsWith(".local");
  } catch { return false; }
}
function Text({ text, sources = [] }: { text: string; sources?: AnswerSearch["sources"] }) {
  return <>{text.split(/(\*\*[^*]+\*\*|\[\d+\])/g).map((part, n) => {
    if (/^\[\d+\]$/.test(part)) {
      const index = Number(part.slice(1, -1)) - 1;
      if (!sources[index]?.source_id || !safeUrl(sources[index].url)) return part;
      const source = sources[index];
      return <a key={n} className="assistant-evidence-link" href={source.url} title={`${source.title} · ${source.read_level === "page_text" ? "已读取正文" : source.read_level === "provider_reference" ? "高德参考信息" : "搜索摘要"}`} aria-label={`查看来源：${source.title}`} target="_blank" rel="noopener noreferrer">[{index + 1}]</a>;
    }
    return part.startsWith("**") && part.endsWith("**") ? <strong key={n}>{part.slice(2, -2)}</strong> : part;
  })}</>;
}
function SearchImage({ image }: { image: AnswerSearch["images"][number] }) {
  const [failed, setFailed] = useState(false);
  const reviewedLocal = image.usage_basis === "reviewed_commons_license" && /^\/api\/v1\/media\/place-images\/[a-z0-9-]+\.jpg$/.test(image.url) && !!image.license_url && safeUrl(image.license_url);
  if (failed || (!safeUrl(image.url) && !reviewedLocal) || !safeUrl(image.source_url)) return null;
  const reference = !!image.topic && image.description.startsWith(image.topic + "参考图");
  return <figure><a href={image.source_url} target="_blank" rel="noopener noreferrer"><img src={image.url} alt={image.description} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} /></a>{reference && <span className="assistant-photo-kind">参考图</span>}<details className="assistant-photo-credit"><summary aria-label="图片来源与许可">ⓘ</summary><small>{reviewedLocal ? image.attribution : image.description} · <a href={image.source_url} target="_blank" rel="noopener noreferrer">图片来源</a>{reviewedLocal && <> · <a href={image.license_url} target="_blank" rel="noopener noreferrer">{image.license_name || "授权说明"}</a>{image.changes ? ` · ${image.changes}` : ""}</>}</small></details></figure>;
}
export function AssistantAnswer({ text, search }: { text: string; search?: AnswerSearch }) {
  const paragraphs = text.split(/\n\s*\n/);
  const usable = search?.status === "available" && search.sources.length > 0;
  return <div className="assistant-answer-content">
    {paragraphs.map((paragraph, n) => <div key={n}><p><Text text={paragraph} sources={usable ? search.sources : []} /></p>
      {n === 0 && usable && search.images.length > 0 && <div className="assistant-answer-images">{search.images.filter(i => !i.topic || text.includes(i.topic) || (i.place_id && search.sources.some(s => s.place_id === i.place_id))).slice(0, 3).map(i => <SearchImage key={i.url} image={i} />)}</div>}
    </div>)}
    {usable && <details className="ai-thinking"><summary>参考链接</summary><ul>{search.sources.filter(s => safeUrl(s.url)).map((s, index) => <li key={s.source_id || s.url}><a href={s.url} target="_blank" rel="noopener noreferrer">[{index + 1}] {s.title || "查看来源"}</a>{s.read_level && <small> · {s.read_level === "page_text" ? "已读取正文" : s.read_level === "provider_reference" ? "高德参考信息" : "仅搜索摘要"}</small>}</li>)}</ul></details>}
    {search?.status === "unavailable" && <p className="travel-assistant-status">这次联网搜索暂不可用，可以稍后重试。</p>}
  </div>;
}
