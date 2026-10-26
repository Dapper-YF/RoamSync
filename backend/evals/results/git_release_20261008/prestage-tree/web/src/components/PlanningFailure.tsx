import { planningErrorMessage } from "../utils/planningMessages";
import type { PlanningRun } from "../domain/types";

export function PlanningFailure({ run, onRetry, onSuggestion, disabled }: {
  run: PlanningRun;
  onRetry: () => void;
  onSuggestion: (request: string) => void;
  disabled: boolean;
}) {
  const issues = (run.errorDetails?.validation_errors ?? []).filter((issue, index, all) => all.findIndex((other) => other.code === issue.code && other.message === issue.message) === index);
  const codes = new Set(issues.map((issue) => issue.code));
  const timing = [...codes].some((code) => ["route_travel_time_conflict", "time_overlap", "outside_daily_window"].includes(code))
    || /route_travel_time_conflict/.test(run.errorMessage ?? "");
  const budget = [...codes].some((code) => code.includes("budget"));
  const incomplete = codes.has("missing_plan_days");
  const pace = codes.has("relaxed_pace_increased_stops");
  const routeUnavailable = codes.has("route_unavailable");
  const contractFailure = run.errorCode === "planner_invalid_output";
  const message = contractFailure ? "这次方案生成失败，我没有应用任何更改。可以重试本次需求。" : run.errorCode === "planner_constraints_unsatisfied"
    ? "这次安排仍有冲突，尚未保存到行程。"
    : planningErrorMessage(run.errorMessage ?? "暂时没有生成方案，请重试。");
  const suggest = (text: string) => onSuggestion(`${run.userRequest}\n补充要求：${text}`);
  return <div className="ai-message agent error" role="alert">
    <strong>{message}</strong>
    {!contractFailure && issues.length > 0 && <ul>{issues.slice(0, 5).map((issue, index) => <li key={`${issue.code}-${index}`}>{issue.message}</li>)}</ul>}
    {timing && <p>需要重新协调游览与交通时间。重试会保留你的原始需求，不会自动改成减少地点或只调整某一天。</p>}
    {budget && <p>可以减少收费地点，或在旅行设置中调整预算。</p>}
    {routeUnavailable && <p>系统已尝试修正一次。可更换无法到达的补充地点；若接受包车或自驾，请先在旅行偏好中启用相应交通方式，再重新规划。</p>}
    <div className="ai-recovery-actions">
      {timing && <button type="button" disabled={disabled} onClick={onRetry}>按原需求重试</button>}
      {budget && <button type="button" disabled={disabled} onClick={() => suggest("减少收费地点，优先选择免费地点，并保持原预算上限。")}>优先安排免费地点</button>}
      {incomplete && <button type="button" disabled={disabled} onClick={() => suggest("请覆盖旅行中的每一天，补齐没有安排的日期。")}>补齐缺少的日期</button>}
      {pace && <button type="button" disabled={disabled} onClick={() => suggest("减少当天的地点数量，留出更多休息时间。")}>减少当天安排</button>}
      {routeUnavailable && <button type="button" disabled={disabled} onClick={() => suggest("保留原有主要游览与交通偏好，更换无法到达的新增地点。数量无法兼顾时明确解释，不能虚构交通路线或重复景点。")}>更换不可达的补充景点</button>}
      {!timing && !budget && !incomplete && !pace && !routeUnavailable && <button type="button" disabled={disabled} onClick={onRetry}>重试本次需求</button>}
    </div>
  </div>;
}

