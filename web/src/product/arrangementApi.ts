import type { AssistantSession } from "../domain/types";

export type Choice = { id: string; kind: "selected" | "optional" | "free_window" | "cancelled"; label: string; source_ref: string; decision_ref: string; place_id: string | null; day_date: string | null; start: string | null; end: string | null; activity_id: string | null };
export type Activity = { id: string; place_id: string; name: string; display_name: string; scheduled_time: string; duration_minutes: number; schedule_locked: boolean; version: number; note: string | null };
export type Arrangement = { version: number; trip: { id: string; title: string; destination: string; start_date: string; end_date: string; version: number }; days: { id: string; date: string; activities: Activity[]; route_legs: { duration_minutes: number; is_estimated: boolean }[] }[]; items: Choice[] };
export type Run = { id: string; status: string; base_trip_version?: number; error_message: string | null; response_text: string | null; pending_interrupt?: { kind: string; revision_id?: string; questions?: string[] } | null };
export type Revision = { planning_goals?: { hard_goals?: { max_walking_minutes?: number | null } }; goal_satisfaction?: { results: { evidence: Record<string, unknown> }[] }; id: string; status: string; reason: string; proposed_snapshot: { activities: { candidate_id: string; replaces_activity_id: string | null; place_candidate_id: string; day_date: string; planned_start_time: string; duration_minutes: number; reason?: string }[]; route_legs?: { duration_minutes: number; provider: string; is_estimated: boolean }[] }; validation_result: { warnings?: { message: string }[] } };
export type PlaceResult = { name: string; provider_place_id: string; address?: string; neighborhood?: string; description?: string; [key: string]: unknown };
export const clock = (v?: string | null) => v?.slice(0, 5) ?? "";
export const choiceLabels: Record<string, string> = { selected: "已选 · 时间未定", optional: "备选 · 可以不去", free_window: "保留空闲", cancelled: "已撤销", appointment: "你提供的固定预约" };

export async function assistantRequest<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${url}`, { ...init, headers: { "Content-Type": "application/json", ...init?.headers } });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(response.status === 409 ? "这份安排刚刚有了新修改。本次操作没有覆盖它，请刷新并核对后再试。" : typeof body.detail === "string" ? body.detail : body.detail?.message ?? "暂时无法完成操作，请稍后重试。");
  }
  return response.status === 204 ? undefined as T : response.json();
}

// This is a permission declaration, not an intent classifier. The server still
// grounds the current utterance and validates all mutations and version fences.
export function arrangementAction(message: string, arrangement: Arrangement, messageId: string, revision?: Revision) {
  const simple = /改成备选|改为备选|设为备选|作为备选|^(?:请)?保留|^(?:今天)?(?:不想去|不去|取消)/.test(message)
    || /^[^，。；]+(?:还是|仍是|仍为)备选(?:[，,](?:不要|别)(?:把它)?排进去)?[。！! ]*$/.test(message);
  const adopt = /^(?:就按这份来|就这样安排|采用这份方案|确认采用)[。！! ]*$/.test(message);
  const reschedule = /改期|(?:日期|出发|返程).{0,8}(?:改到|改为|调整到)|(?:改到|改为)(?:明天|后天|下周|\d{4}[-年]|\d{1,2}月)/.test(message);
  return { trip_id: arrangement.trip.id, expected_version: arrangement.version, operation: adopt && revision ? "accept_plan" : reschedule ? "reschedule_trip" : simple ? "edit_arrangement" : "plan_trip", authorization_message_id: messageId,
    ...(adopt && revision ? { revision_id: revision.id } : {}) };
}

export type ReceiveSession = (session: AssistantSession) => void;
