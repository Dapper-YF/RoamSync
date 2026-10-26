export function ResearchEvidence({ value }: { value: unknown }) {
  if (!value || typeof value !== "object" || !("places" in value) || !value.places || typeof value.places !== "object") return null;
  const sources = new Map<string, string>();
  for (const place of Object.values(value.places)) {
    if (!place || typeof place !== "object" || !Array.isArray(place.sources)) continue;
    for (const source of place.sources) {
      if (typeof source?.url !== "string" || typeof source?.title !== "string") continue;
      try { if (["http:", "https:"].includes(new URL(source.url).protocol)) sources.set(source.url, source.title); } catch { /* Invalid source is omitted. */ }
    }
  }
  if (!sources.size) return null;
  return <details className="ai-facts"><summary>景点选择的网页依据（{sources.size} 条）</summary>
    <p>检索摘要用于了解特色与代表性；开放时间、预约和票价请以景区最新公告为准。</p>
    {"queried_at" in value && typeof value.queried_at === "string" && <small>检索时间：{value.queried_at}</small>}
    {[...sources].map(([url, title]) => <a key={url} href={url} target="_blank" rel="noopener noreferrer">{title || "查看来源"}</a>)}
  </details>;
}
