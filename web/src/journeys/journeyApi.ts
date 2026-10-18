import { DraftRepository, type Draft } from "../data/draftRepository";
import type { ExplorePoint } from "../domain/explore";

export interface JourneyAssistantContext {
  tripId?: string;
  draftContext?: { draftId: string; version: number; city: string; requirements: string; plan: unknown };
  prompt?: string;
  city?: string;
}
export interface JourneyPageProps {
  onAskAssistant?: (context: JourneyAssistantContext) => void;
  onRoute?: (context: { from?: ExplorePoint; to: ExplorePoint; city: string; returnTo: string; fromName?: string; toName?: string; tripId?: string; activityId?: string; fromActivityId?: string }) => void;
}
export class JourneyDraftRepository extends DraftRepository {
  async edit(draft: Draft, values: { title?: string; requirements?: string; plan?: Draft["plan"] }): Promise<Draft> {
    return draftPost(`/${draft.id}/edit`, { expected_version: draft.version, ...values });
  }
  async scopedRun(draft: Draft, requirements: string, targetDayIndices?: number[], requestId: string = crypto.randomUUID()): Promise<Draft> {
    return draftPost(`/${draft.id}/runs`, { expected_version: draft.version, request_id: requestId, requirements, target_day_indices: targetDayIndices });
  }
}
async function draftPost(path: string, body: unknown): Promise<Draft> {
  const response = await fetch(`/api/v1/drafts${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail?.message ?? (response.status === 409 ? "草稿已在别处更新。你的编辑仍保留，请读取最新版本后核对。" : "草稿修改暂不可用，请保留编辑并重试。"));
  }
  return response.json();
}
export const journeyDrafts = new JourneyDraftRepository();
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : "暂时无法完成，请重试。";
export function tripPhase(trip: { status?: string; startDate: string; endDate: string }, today: string) {
  if (["archived", "completed"].includes(trip.status || "") || trip.endDate < today) return "history";
  return trip.status === "active" || trip.startDate <= today ? "active" : "upcoming";
}
export function localDate() { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date()); }

