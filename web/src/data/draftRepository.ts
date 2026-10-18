export interface DraftItem { name: string; note: string; place_id: string | null; identity_status: "provider_confirmed" | "unknown" }
export interface DraftDay { day_index: number; title: string; items: DraftItem[] }
export interface DraftRun { id: string; request_id: string; status: "running" | "completed" | "failed" | "cancelled" | "interrupted"; requirements: string; source: "model" | "fixture"; error: string | null; created_at: string; finished_at: string | null; lease_expires_at?: string | null }
export interface Draft { id: string; title: string; city: string; day_count: number; requirements: string; version: number; status: "active" | "cancelled"; saved: boolean; plan: { days: DraftDay[] } | null; runs: DraftRun[]; updated_at: string }

export class DraftRepository {
  private async request<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(`/api/v1/drafts${path}`, body === undefined ? undefined : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail?.message ?? "草稿服务暂不可用，请重试。");
    }
    return response.json();
  }
  list() { return this.request<Draft[]>(""); }
  get(id: string) { return this.request<Draft>(`/${encodeURIComponent(id)}`); }
  create(data: { city: string; title: string; day_count: number; requirements: string }) { return this.request<Draft>("", data); }
  run(draft: Draft, requirements: string, requestId = crypto.randomUUID()) {
    return this.request<Draft>(`/${draft.id}/runs`, { expected_version: draft.version, request_id: requestId, requirements });
  }
  action(draft: Draft, action: "save" | "cancel" | "restore" | "cancel-run") {
    return this.request<Draft>(`/${draft.id}/${action}`, { expected_version: draft.version });
  }
}
