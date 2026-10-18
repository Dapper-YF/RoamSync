import { useEffect, useState } from "react";

interface Preferences { version: "travel-preferences-v1"; preferred_categories: string[]; interests: string[] }
export function PreferencePanel({ onSaved }: { onSaved?: () => void }) {
  const [value, setValue] = useState<Preferences>({ version: "travel-preferences-v1", preferred_categories: [], interests: [] });
  const [interests, setInterests] = useState("");
  const [message, setMessage] = useState("");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/me/travel-preferences", { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error("偏好服务暂不可用，请稍后重新打开。");
      const pref = await response.json() as Preferences;
      setValue(pref); setInterests(pref.interests.join("，")); setReady(true);
    }).catch(error => { if (!controller.signal.aborted) setMessage(error.message); });
    return () => controller.abort();
  }, []);
  const save = async () => {
    setBusy(true); setMessage("");
    try {
      const body = { ...value, interests: interests.split(/[,，]/).map(term => term.trim()).filter(Boolean) };
      const response = await fetch("/api/v1/me/travel-preferences", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!response.ok) throw new Error("保存失败。最多8个兴趣，每个不超过30字，请检查后重试。");
      setValue(await response.json()); setMessage("偏好已保存，下次探索会优先显示匹配地点。"); onSaved?.();
    } catch (error) { setMessage(error instanceof Error ? error.message : "保存失败，请重试。"); }
    finally { setBusy(false); }
  };
  return <section className="rxp-preferences" aria-label="显式旅行偏好"><h3>我的探索偏好</h3><p>只使用你在这里明确保存的选择，按地点名称与类别匹配排序，不推断饮食或住宿需求。</p>
    <div className="rxp-filter-row">{[["attraction", "风景名胜"], ["food", "餐饮美食"], ["lodging", "住宿"]].map(([key, label]) => <label key={key}><input type="checkbox" disabled={!ready} checked={value.preferred_categories.includes(key)} onChange={event => setValue({ ...value, preferred_categories: event.target.checked ? [...value.preferred_categories, key] : value.preferred_categories.filter(item => item !== key) })} />{label}</label>)}</div>
    <label>兴趣关键词（逗号分隔）<input aria-label="兴趣关键词" value={interests} disabled={!ready} onChange={event => setInterests(event.target.value)} placeholder="例如：博物馆，茶馆" /></label>
    <button className="rxp-secondary-action" type="button" disabled={!ready || busy} onClick={() => void save()}>{busy ? "正在保存" : "保存探索偏好"}</button>
    {message && <p role="status">{message}</p>}
  </section>;
}
