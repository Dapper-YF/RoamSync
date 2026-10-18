export interface PreviewInput {
  expected_version: number; start_date: string; total_budget_fen: number | null; daily_budget_fen: number | null;
  transport_mode: "walk" | "driving"; duration_minutes: number; unknown_cost_estimate_fen: number; operation_id?: string;
}
export interface PreparedPlan {
  id: string; draft_id: string; draft_version: number; operation_id: string | null; prepared_hash: string; content_hash: string; evidence_hash: string;
  title: string; city: string; requirements: string; constraints: PreviewInput; end_date: string; expires_at: string;
  activities: { ref: string; day_date: string; position: number; name: string; place_id: string | null;
    planned_start_time: string; duration_minutes: number; transport_mode: string; estimated_cost_fen: number;
    cost_nature: "provider_reference" | "planning_estimate"; note: string }[];
  routes: { day_date: string; from_ref: string; to_ref: string; route: { mode: string; distance_meters: number; duration_seconds: number } }[];
  coverage: { checked: string[]; missing: string[]; blockers: string[] };
}
export interface PromotionOperation {
  id: string; draft_id: string; draft_version: number; prepared_id: string; prepared_hash: string;
  allowed_action: "create_only" | "create_and_adopt"; status: "requested" | "trip_created" | "awaiting_apply" | "needs_review" | "applied" | "created" | "failed" | "cancelled";
  stage: string; target_trip_id: string | null; target_revision_id: string | null; target_run_id: string | null;
  error: string | null; consumed_at: string | null; expires_at: string; validation?: { valid: boolean; errors: { code: string; message: string }[] } | null;
}
export class DraftPromotionRepository {
  private async request<T>(path: string, body?: unknown): Promise<T> {
    const response = await fetch(`/api/v1${path}`, body === undefined ? undefined : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail?.message ?? (response.status === 422 ? "请检查出发日期格式、预算和时长后重试。" : "旅行转换暂时不可用，请刷新当前操作后重试。"));
    }
    return response.json();
  }
  preview(draftId: string, input: PreviewInput) { return this.request<PreparedPlan>(`/drafts/${draftId}/promotion-preview`, input); }
  list(draftId: string) { return this.request<PromotionOperation[]>(`/drafts/${draftId}/promotions`); }
  confirm(plan: PreparedPlan, action: "create_only" | "create_and_adopt", requestId: string) {
    return this.request<PromotionOperation>(plan.operation_id ? `/draft-promotions/${plan.operation_id}/review` : "/draft-promotions", {
      request_id: requestId, prepared_id: plan.id, prepared_hash: plan.prepared_hash, action,
      confirmation: action === "create_only" ? "创建旅行" : "创建并采用当前方案",
    });
  }
  resume(id: string) { return this.request<PromotionOperation>(`/draft-promotions/${id}/resume`, {}); }
  cancel(id: string) { return this.request<PromotionOperation>(`/draft-promotions/${id}/cancel`, {}); }
}
