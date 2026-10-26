import type { PlanRevision } from "../domain/types";

export function PlanningGoalCard({ revision }: { revision: PlanRevision }) {
  const goals = revision.planningGoals;
  const results = revision.goalSatisfaction?.results ?? [];
  if (!goals || (!goals.hardGoals.endBefore && goals.hardGoals.maxWalkingMinutes == null && !goals.softGoals.pace && !goals.softGoals.minimizeWalking && !goals.softGoals.preserveExisting)) return null;
  return <section className="planning-goal-card" aria-label="本次规划目标与方案检查结果">
    <strong>本次规划目标</strong>
    <ul>
      {goals.hardGoals.endBefore && <li>{goals.hardGoals.endBefore} 前结束</li>}
      {goals.hardGoals.maxWalkingMinutes != null && <li>步行不超过 {goals.hardGoals.maxWalkingMinutes} 分钟</li>}
      {goals.softGoals.pace === "relaxed" && <li>轻松节奏</li>}
      {goals.softGoals.minimizeWalking && <li>尽量少走路</li>}
      {goals.softGoals.preserveExisting && <li>尽量保留现有活动</li>}
    </ul>
    <strong>方案检查结果</strong>
    <ul className="goal-result-list">
      {results.map((result) => <li key={result.goal} className={`goal-${result.status}`}>
        <span aria-hidden="true">{result.status === "satisfied" ? "✓" : result.status === "unsatisfied" ? "!" : "△"}</span>
        {label(result.goal, result.evidence)}
      </li>)}
    </ul>
  </section>;
}

function label(goal: string, evidence: Record<string, unknown>) {
  if (goal === "end_before") return `结束时间：${String(evidence.candidate_end ?? "未生成")}（要求 ${String(evidence.required_end_before)} 前）`;
  if (goal === "max_walking_minutes") return `步行：${String(evidence.candidate_walking_minutes)} 分钟（上限 ${String(evidence.limit_minutes)} 分钟）`;
  if (goal === "minimize_walking") return `步行变化：${String(evidence.before_walking_minutes)} → ${String(evidence.after_walking_minutes)} 分钟`;
  if (goal === "preserve_existing") return `保留 ${String(evidence.preserved_count)}/${String(evidence.before_activity_count)} 个原活动`;
  if (goal === "pace_relaxed") return `轻松节奏：活动 ${String(evidence.activity_count_before)} → ${String(evidence.activity_count_after)} 项`;
  return goal;
}
