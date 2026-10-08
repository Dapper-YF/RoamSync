import type { PlanRevision } from "../domain/types";

type Entry = {
  decision_id: string;
  action_type: string;
  activity_name: string;
  reason: string;
  before?: Record<string, unknown>;
  after?: Record<string, unknown>;
  evidence_status: string;
};

const actions: Record<string, string> = {
  preserve: "保留", remove: "移出", add: "新增", move: "调整时间",
  shorten: "缩短停留", extend: "延长停留", change_travel_mode: "调整交通方式",
};

function detail(entry: Entry): string | null {
  if (entry.action_type === "shorten" || entry.action_type === "extend") {
    const before = entry.before?.duration_minutes;
    const after = entry.after?.duration_minutes;
    if (typeof before === "number" && typeof after === "number") return `${before} → ${after} 分钟`;
  }
  if (entry.action_type === "move") {
    const before = entry.before?.start_time;
    const after = entry.after?.start_time;
    if (typeof before === "string" && typeof after === "string") return `${before} → ${after}`;
  }
  return null;
}

export function DecisionSummary({ revision }: { revision: PlanRevision }) {
  const raw = revision.differenceSummary.decision_summary;
  const summary = raw && typeof raw === "object" ? raw as { status?: string; entries?: Entry[] } : null;
  if (summary?.status === "invalid") {
    return <p className="decision-summary" role="status">调整原因暂未通过核验</p>;
  }
  const entries = summary?.status === "validated" && Array.isArray(summary.entries)
    ? summary.entries.filter((entry) => entry.evidence_status === "validated") : [];
  return <details className="decision-summary">
    <summary>为什么这样调整？</summary>
    {entries.length === 0 ? <p>暂无结构化调整依据</p> : <ul>{entries.map((entry) => <li key={entry.decision_id}>
      <strong>{actions[entry.action_type] ?? "调整"} {entry.activity_name}</strong>
      {detail(entry) && <span> · {detail(entry)}</span>}
      <p>原因：{entry.reason}</p>
    </li>)}</ul>}
  </details>;
}
