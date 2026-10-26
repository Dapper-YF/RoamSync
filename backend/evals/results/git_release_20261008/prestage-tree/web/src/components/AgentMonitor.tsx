import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import "./AgentMonitor.css";
import { MONITOR_CHANNEL, type DialogueObservation } from "../utils/agentMonitorChannel";

export interface MonitorRun {
  id: string; trip_id: string; trip_title: string; status: string; intent: string | null;
  base_trip_version: number; current_trip_version: number; model: string | null; provider: string | null;
  created_at: string; started_at: string | null; completed_at: string | null; planning_finished_at?: string | null;
}
export interface MonitorStage {
  id: string; title: string; status: string; started_at: string | null; completed_at: string | null;
  duration_ms: number | null; attempts: number; source: string; data: Record<string, unknown>;
}
export interface MonitorTool {
  id: string; stage: string; provider: string | null; purpose: string | null; status: string;
  started_at: string; duration_ms: number | null; input: Record<string, unknown>; output: Record<string, unknown>;
}
export interface MonitorTrace {
  contract_version: number; run: MonitorRun; stages: MonitorStage[]; tools: MonitorTool[];
  events: Array<Record<string, unknown>>; limitations: string[]; observations_truncated: boolean;
  error: { code: string; message: string; stage: string | null } | null;
  active_stage?: string;
}
export interface MonitorClient {
  runs: (tripId: string, signal: AbortSignal) => Promise<MonitorRun[]>;
  trace: (id: string, signal: AbortSignal) => Promise<MonitorTrace>;
  dialogue?: (sessionId: string, messageId: string, signal: AbortSignal) => Promise<DialogueTrace>;
  trips?: (signal: AbortSignal) => Promise<Array<{ id: string; title: string }>>;
}
interface DialogueTrace {
  status: string; source: string;
  events: Array<{ sequence: number; stage: string; status: string; at: string; duration_ms: number | null }>;
}
async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(path.startsWith("/") ? path : `/api/v1/agent-monitor/${path}`, { signal });
  if (!response.ok) throw new Error(`监控 API 请求失败：${response.status}`);
  return response.json() as Promise<T>;
}
const api: MonitorClient = {
  runs: (tripId, signal) => get(`runs?limit=60${tripId ? `&trip_id=${encodeURIComponent(tripId)}` : ""}`, signal),
  trace: (id, signal) => get(`runs/${encodeURIComponent(id)}`, signal),
  dialogue: (sessionId, messageId, signal) => get(`sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}`, signal),
  trips: (signal) => get("/api/v1/trips", signal),
};
const object = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const rows = (value: unknown): Array<Record<string, unknown>> => Array.isArray(value) ? value.map(object) : [];
const chinese: Record<string, string> = {
  pending: "待执行", running: "执行中", completed: "已完成", failed: "失败", skipped: "已跳过", unavailable: "不可用",
  queued: "已排队", researching: "研究中", planning: "规划中", validating: "验证中", awaiting_confirmation: "等待用户确认",
  awaiting_clarification: "等待用户补充", accepted: "已接受", rejected: "已拒绝", answered: "已回答", cancelled: "已取消", superseded: "已被替代",
  PASS: "通过", FAIL: "不通过", "N/A": "不适用", satisfied: "已满足", unsatisfied: "未满足", not_evaluable: "无法评估", validated: "已验证", invalid: "无效",
  relaxed: "轻松", balanced: "均衡", intensive: "紧凑", afternoon: "下午", morning: "上午", evening: "晚上", walk: "步行", transit: "公共交通", driving: "驾车",
  replan_trip: "重新规划旅行", modify_day: "调整当日行程", create_plan: "创建行程", plan_preview: "生成候选方案", answer: "直接回答", clarify: "请求补充信息", reject: "拒绝执行",
  true: "是", false: "否", available: "可用", partial: "部分可用", not_required: "无需执行", not_configured: "未配置", disabled_in_test: "测试环境禁用",
  message: "用户请求", planning_request: "规划请求", received_at: "接收时间", entry_point: "请求入口", current_activity_id: "当前活动", assistant_session_id: "会话编号",
  goal_routing: "目标分流", planning_brief: "规划摘要", target_days: "目标日期", requested_pace: "期望节奏", target_period: "目标时段",
  hard_goals: "硬约束", soft_goals: "偏好目标", must_keep: "必须保留", end_before: "最晚结束时间", max_walking_minutes: "步行上限（分钟）", source_text: "原始文本",
  intent_type: "意图类型", route: "执行路径", operation_mode: "操作权限", target: "作用范围", requires_clarification: "是否需要补充", confidence: "置信度",
  grounded_intent: "已绑定的意图", primary_intent: "主要意图", operation_types: "操作类型", target_day_ids: "目标日编号", target_activity_ids: "目标活动编号",
  places: "地点", sources: "证据来源", source_count: "来源数量", title: "标题", url: "来源链接", content: "来源摘要", query: "检索词", queried_at: "查询时间",
  research: "目的地研究", external_facts: "外部事实", search: "检索结果", weather: "天气结果", reason: "结果说明", prominence: "代表性依据",
  status: "状态", id: "编号", number: "版本编号", provider: "服务商", model: "模型", token_usage: "Token 用量", purpose: "调用目的", duration_ms: "耗时（毫秒）",
  candidate_activity_count: "候选活动数量", route_count: "路线数量", result_count: "返回地点数量", route_legs: "路线分段", scope: "观测范围", error_code: "错误代码",
  decision_summary: "决策结果", entries: "决策条目", error_codes: "错误代码", candidate: "候选方案", goals: "目标", validation: "验证结果", valid: "是否有效", errors: "错误", warnings: "提示",
  goal_satisfaction: "目标满足情况", results: "检查结果", goal: "目标", details: "依据", message_id: "请求编号", candidate_id: "候选活动编号",
  before: "原行程", proposed: "建议行程", difference: "差异", change_summary: "变更说明", schedule_adjustments: "时间调整", planned_total_fen: "预计总费用（分）", planned_budget_delta_fen: "费用变化（分）",
  base_trip_version: "规划时行程版本", accepted_trip_version: "接受后行程版本", decided_at: "决定时间", revision_id: "候选版本编号", feedback_persisted: "反馈已保存", feedback: "用户反馈", reason_code: "反馈类型", reason_text: "反馈内容", clarification: "待补充信息",
  "Formal Itinerary": "正式行程", "Trip Version": "行程版本", "Current Execution State": "当前执行状态", "User Preferences": "用户偏好",
  "Must-do Activities": "必须完成的活动", "Locked Activities": "已锁定活动", "Travel Events": "旅行事件", "Navigation ETA": "导航预计到达时间", Slack: "剩余时间余量",
  "Previous Revision / Reject Feedback": "历史候选版本 / 拒绝反馈", "Research Candidates": "候选地点", "Route Facts": "路线事实", "Decision Context Provenance": "上下文数据来源",
  "Time Windows": "时间窗口", "Activity Overlap": "活动时间重叠", "Protected Activities": "受保护活动", "Route Feasibility": "路线可行性", "Budget Constraint": "预算约束",
  "Destination Research": "目的地研究", "POI Search": "地点检索", "Generate Candidate": "生成候选方案", "Travel-date weather": "旅行日期天气",
  "Resolve sourced destination candidates": "研究有来源的候选地点", "Route enrichment (includes persisted cache lookup)": "补充路线事实（含缓存查询）",
  "Enrichment including cache; individual HTTP calls not captured": "包含路线缓存读取；未记录逐次 HTTP 请求",
  "Old runs have no per-stage latency or tool-call history.": "旧运行未保存逐阶段耗时和逐次 tool 调用记录。",
  "revision / checkpoint / run": "候选版本 / 持久化检查点 / 运行记录", "execution decision": "已记录的执行分支", "progress.events": "持久化观测事件",
  day_date: "日期", planned_start_time: "开始时间", duration_minutes: "时长（分钟）", name: "名称", display_name: "显示名称", from_activity_ref: "起点活动", to_activity_ref: "终点活动", distance_meters: "距离（米）", is_estimated: "是否估算", mode: "交通方式",
  interpret_goal: "理解对话目标", resolve_conversation: "绑定对话对象", determine_information_need: "确定信息需求", gather_read_only_context: "读取上下文与知识", generate_interaction: "生成回答与建议", extract_interaction_outcome: "提取结构化交互结果", planning_handoff_not_authorized: "保留用户规划授权边界", prepare_conversation_persistence: "保存对话结果",
  research_decision: "研究分支决策", goal_check: "目标约束检查", end_before_time: "最晚结束时刻", pace: "期望节奏", minimize_walking: "减少步行", preserve_existing: "保留现有活动", evidence: "验证依据", minimum_slack_minutes: "最小时间余量（分钟）", walking_before_minutes: "调整前步行（分钟）", walking_after_minutes: "调整后步行（分钟）", route_before_minutes: "调整前交通（分钟）", route_after_minutes: "调整后交通（分钟）", rationale_verified: "原因是否已验证", supporting_evidence: "支持事实", goal_refs: "目标引用", memory_refs: "历史反馈引用", semantic_refs: "活动语义引用", action_type: "操作类型", primary_reason: "主要依据", before_minutes: "调整前（分钟）", after_minutes: "调整后（分钟）", delta_minutes: "变化（分钟）", code: "代码", source_revision_ids: "历史候选版本编号", source_run_ids: "历史运行编号", count: "数量", provenance: "数据来源",
  available_minutes: "可用时间（分钟）", required_minutes: "所需时间（分钟）", fact_refs: "事实引用", action: "操作", source: "来源", protected_activity_ids: "受保护活动编号", editable_activity_ids: "可编辑活动编号", protected_constraints: "受保护约束",
  run: "运行记录", checkpoint: "持久化检查点", travel_goal_routing: "对话目标分流",
  gather_context: "读取上下文与知识", generate: "生成回答与建议", extract_outcome: "提取结构化交互结果", handoff_boundary: "检查规划授权边界", prepare_persistence: "准备保存对话结果",
  response_returned: "对话结果已保存并返回", request_failed: "对话请求失败", poi: "地点匹配", planner: "规划与候选方案", validator: "确定性验证", revision: "候选行程版本", user_decision: "用户决策",
  matched_count: "匹配数量", observation: "观测记录", process_local: "当前服务阶段观测",
  companion_model: "调用回答模型（tool）", knowledge_tool: "调用知识检索（tool）", assistant_tool_routing: "选择旅行 tool",
  preview_change: "生成候选变更", read_only: "只读", propose_only: "仅提出建议", risk_level: "风险级别", low: "低", medium: "中等", high: "高",
  requires_confirmation: "是否需要确认", parser_version: "解析规则版本", trip_id: "旅行编号", day_id: "旅行日编号", activity_id: "活动编号",
  request: "请求内容", policy_decision: "执行权限与分流", constraints: "约束", candidate_place_ids: "候选地点编号",
  unresolved_activity_mentions: "未匹配的活动", unresolved_place_mentions: "未匹配的地点", missing_fields: "缺少的信息", ambiguities: "待澄清内容",
  budget_must_not_increase: "预算是否禁止增加", max_additional_cost_fen: "费用增加上限（分）", preferred_environment: "偏好环境", weather_sensitive: "是否受天气影响", preserve_completed: "保留已完成活动",
  requested_place_queries: "待查询地点", requested_date: "期望日期", selected_day_id: "选中的旅行日", selected_activity_id: "选中的活动",
  source_goal: "来源目标", protected_activity_refs: "受保护活动引用", requested_change: "请求的变更", available_count: "可用数量",
  destination_research_required: "是否需要目的地研究", operations: "操作列表", interests: "兴趣", destination: "目的地", outdoor: "户外", indoor: "室内", normal: "普通",
  must_do: "必须完成", planned: "计划中", category: "类别", rationale_status: "依据验证状态", rationale_unavailable: "原始依据不可用",
  accepted_at: "接受时间", rejected_at: "拒绝时间", activity_count: "活动数量", activity_names: "活动名称", source_refs: "来源引用", removed: "移除", kept: "保留", shortened: "缩短", moved: "移动",
};
const label = (value: unknown): string => value == null ? "不可用" : typeof value === "object" ? JSON.stringify(value) : chinese[String(value)] ?? String(value);
const fieldLabel = (key: string) => chinese[key] ?? (/^[a-zA-Z][a-zA-Z0-9_ -]*$/.test(key) ? "补充信息" : key);
const stageTitles: Record<string, string> = { message: "用户请求", intent: "意图理解", goal: "目标提取", context: "上下文构建", research: "目的地研究", poi: "地点匹配", planner: "规划与候选方案", route: "路线事实补充", validator: "确定性验证", revision: "候选行程版本", user_decision: "用户决策" };
const stageTitle = (stage: MonitorStage) => stageTitles[stage.id] ?? label(stage.title);
const stageStatus = (stage: MonitorStage) => stage.id === "user_decision" && stage.status === "running" ? label(stage.data.status) : label(stage.status);
const clock = (value: string | null) => value && Number.isFinite(new Date(value).getTime()) ? new Date(value).toLocaleTimeString("zh-CN", { hour12: false }) : "—";
const latency = (value: number | null) => value == null ? "耗时未记录" : value >= 1000 ? `${(value / 1000).toFixed(2)} 秒` : `${value} 毫秒`;
const elapsed = (start: string) => `已执行 ${Math.max(0, (Date.now() - new Date(start).getTime()) / 1000).toFixed(1)} 秒`;
const symbols: Record<string, string> = { pending: "○", running: "◉", completed: "●", failed: "×", skipped: "↷", unavailable: "—" };
const explanations: Record<string, string> = {
  message: "用户只输入自然语言；这里保留原始输入与实际规划请求 的对应关系。",
  intent: "这一阶段决定用户是在查询、探索、创建计划还是修改现有旅行。耗时覆盖整个意图解析节点，包括其中执行的研究 tool。",
  goal: "结构化目标和硬约束来自后端提取结果。页面不会根据候选方案猜测目标。",
  context: "Agent 的能力也取决于决策时取得的正确状态与事实。这里展示当次运行保存的上下文。",
  research: "只有实际需要发现地点时才研究目的地。来源是证据，开放时间等运营事实仍需核实。",
  poi: "搜索获得的地点名称需要地图匹配；已存在的正式地点可能被直接复用。",
  planner: "规划模型根据目标、偏好和候选事实提出方案。结构化决定来自后端，原因可用性由决策记录标注。",
  route: "规划模型说可以去，还需要路线事实支持。此阶段可能复用路线缓存，不代表每段都重新请求 AMap。",
  validator: "确定性程序重新验证时间、路线、预算与受保护活动。该节点包括路线获取与已有时间修复；逐项耗时未单独保存。",
  revision: "验证通过后形成候选行程版本；正式行程仍等待用户决定。",
  user_decision: "Agent 有建议权；正式行程只有用户接受方案后才能更新。",
};

function JsonDetail({ title, value, presentation }: { title: string; value: unknown; presentation: boolean }) {
  if (presentation || value == null) return null;
  return <details className="monitor-json"><summary>{title} · 清理后的 JSON</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>;
}
function Fields({ value }: { value: Record<string, unknown> }) {
  return <dl className="monitor-fields">{Object.entries(value).filter(([, item]) => item == null || typeof item !== "object").map(([key, item]) => <div key={key}><dt title={key}>{fieldLabel(key)}</dt><dd>{label(item)}</dd></div>)}</dl>;
}
function Activities({ activities }: { activities: unknown }) {
  const items = rows(activities);
  if (!items.length) return <p className="monitor-muted">没有保存活动数据。</p>;
  return <table className="monitor-table"><thead><tr><th>日期 / 开始</th><th>活动</th><th>时长</th><th>约束 / 活动编号</th></tr></thead><tbody>{items.map((item, index) => <tr key={index}>
    <td>{label(item.day_date ?? item.date ?? "")} {label(item.planned_start_time ?? item.scheduled_time ?? "—")}</td>
    <td>{label(item.display_name ?? item.name ?? item.place_candidate_id)}</td><td>{label(item.duration_minutes)} 分钟</td>
    <td title={label(item.replaces_activity_id ?? item.id)}>{item.schedule_locked ? "已锁定 · " : ""}{item.importance === "must_do" ? "必须保留 · " : ""}{item.replaces_activity_id || item.id ? `原活动 #${label(item.replaces_activity_id ?? item.id).slice(0, 8)}` : "新增"}</td>
  </tr>)}</tbody></table>;
}
function StageDetail({ stage, presentation }: { stage: MonitorStage; presentation: boolean }) {
  const data = stage.data;
  const json = <JsonDetail title="开发者详情" value={data} presentation={presentation} />;
  if (stage.id === "message") return <><blockquote className="monitor-message">{label(data.message)}</blockquote><Fields value={Object.fromEntries(Object.entries(data).filter(([key]) => !["message", "planning_request"].includes(key)))} />{data.planning_request !== data.message && data.planning_request != null && <p>规划请求：{label(data.planning_request)}</p>}{json}</>;
  if (stage.id === "context") return <><div className="monitor-count">上下文项目： {label(data.available_count)} / {rows(data.items).length}</div><div className="monitor-context">{rows(data.items).map((item) => <div className="monitor-context-item" key={fieldLabel(String(item.label))}><strong>{fieldLabel(String(item.label))}</strong><span className={item.available ? "monitor-good" : "monitor-muted"}>{item.available ? "✓ 可用" : "— 不可用"}</span><JsonDetail title={fieldLabel(String(item.label))} value={item.data} presentation={presentation} /></div>)}</div>{json}</>;
  if (stage.id === "goal") return <><Fields value={data} /><div className="monitor-result-grid">{Object.entries(data).filter(([, value]) => value && typeof value === "object").map(([key, value]) => <section key={key}><h3>{fieldLabel(key)}</h3><Structured value={value} /></section>)}</div>{json}</>;
  if (stage.id === "intent") return <><h3>意图与执行决策</h3><Fields value={object(object(data.request).intent)} /><Fields value={object(data.policy_decision)} /><h3>解析结果</h3><Fields value={data} /><Structured value={data.grounded_intent} />{json}</>;
  if (stage.id === "planner") return <><h3>候选活动</h3><Activities activities={object(data.candidate).activities} /><h3>决策结果</h3><Fields value={object(data.decision_summary)} />{rows(object(data.decision_summary).entries).map((entry, index) => <section className="monitor-evidence" key={index}><Structured value={entry} /></section>)}{json}</>;
  if (stage.id === "route") return <><h3>路线事实</h3><table className="monitor-table"><thead><tr><th>路线分段</th><th>距离</th><th>时间</th><th>交通方式 / 服务商</th></tr></thead><tbody>{rows(data.route_legs).map((leg, index) => <tr key={index}><td>{label(leg.from_name ?? leg.from_activity_ref)} → {label(leg.to_name ?? leg.to_activity_ref)}</td><td>{label(leg.distance_meters)} 米</td><td>{label(leg.duration_minutes)} 分钟</td><td>{label(leg.mode)} / {label(leg.provider)}{leg.is_estimated ? " · 估算" : ""}</td></tr>)}</tbody></table>{!rows(data.route_legs).length && <p>路线事实不可用</p>}{json}</>;
  if (stage.id === "validator") return <><h3>确定性验证</h3><div className="monitor-checks">{rows(data.checks).map((check, index) => <details key={index}><summary><strong>{fieldLabel(String(check.label))}</strong><span className={`check-${String(check.status).toLowerCase()}`}>{label(check.status)}</span></summary><Structured value={check.facts} /></details>)}</div><h3>验证结果</h3><Fields value={object(data.validation)} />{rows(object(data.validation).errors).map((issue, index) => <div className="monitor-error" key={index}><Structured value={issue} /></div>)}{json}</>;
  if (stage.id === "revision") return <><Fields value={data} /><p>{label(data.change_summary)}</p><div className="monitor-comparison"><section><h3>原行程</h3><Activities activities={rows(data.before).flatMap((day) => rows(day.activities).map((item) => ({ ...item, date: day.date })))} /></section><section><h3>建议行程</h3><Activities activities={object(data.proposed).activities} /></section></div><h3>差异</h3><Fields value={object(data.difference)} /><Structured value={object(data.difference).schedule_adjustments} />{json}</>;
  if (stage.id === "user_decision") return <><div className="monitor-permission"><h3>Agent 权限边界</h3><p>✓ 研究 · ✓ 提出方案 · ✓ 验证</p><p>× 未经确认覆盖正式行程</p><strong>正式行程只有用户接受方案后才会更新</strong></div><Fields value={data} />{data.status === "accepted" && <p className="monitor-good">方案已接受 · 行程版本 {label(data.base_trip_version)} → {label(data.accepted_trip_version)} · 正式行程已更新</p>}{data.status === "rejected" && <p>方案已拒绝 · 反馈 {data.feedback_persisted ? "已保存" : "未提供"}</p>}<Structured value={data.clarification} />{json}</>;
  return <><Structured value={data} />{json}</>;
}
function Structured({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value == null) return <p className="monitor-muted">不可用</p>;
  if (depth > 4) return <p className="monitor-muted">详情请查看折叠数据</p>;
  if (Array.isArray(value)) return <div>{value.length === 0 ? <p className="monitor-muted">空列表（真实结果）</p> : value.map((item, index) => <div className="monitor-structured-row" key={index}><Structured value={item} depth={depth + 1} /></div>)}</div>;
  if (typeof value !== "object") return <p>{label(value)}</p>;
  const data = object(value);
  return <><Fields value={data} />{Object.entries(data).filter(([, item]) => item && typeof item === "object").map(([key, item]) => <section className="monitor-nested" key={key}><h4 title={key}>{fieldLabel(key)}</h4><Structured value={item} depth={depth + 1} /></section>)}</>;
}

function DialogueExecution({ trace, fallback, follow, autoStage }: { trace: DialogueTrace | null; fallback?: string[]; follow: boolean; autoStage: boolean }) {
  const currentElement = useRef<HTMLLIElement | null>(null);
  const events = trace?.events ?? [];
  const stages = Array.from(new Map(events.map((event) => [event.stage, event])).values());
  const current = stages.filter((event) => event.status === "running").at(-1) ?? stages.at(-1);
  useEffect(() => {
    if (follow && autoStage) currentElement.current?.scrollIntoView?.({ block: "nearest" });
  }, [follow, autoStage, current?.stage]);
  if (!stages.length && !fallback?.length) return null;
  return <section className="monitor-dialogue-execution" aria-label="对话 Agent 执行阶段">
    <div className="monitor-feed-heading"><h2>对话 Agent 执行阶段</h2><span>{stages.length ? "真实阶段观测" : "后端返回的阶段记录 · 耗时未记录"}</span></div>
    <ol className="monitor-dialogue-stages">{stages.length ? stages.map((event) => <li key={event.stage} data-status={event.status} ref={event.stage === current?.stage ? currentElement : undefined}>
      <span className={`monitor-symbol stage-${event.status}`}>{symbols[event.status]}</span><div><strong>{fieldLabel(event.stage)}</strong><small>{clock(event.at)} · {event.status === "running" ? elapsed(event.at) : latency(event.duration_ms)}</small></div><em className={`stage-${event.status}`}>{label(event.status)}</em>
    </li>) : fallback?.map((name, index) => <li key={`${index}:${name}`}><span className="monitor-symbol stage-completed">●</span><strong>{fieldLabel(name)}</strong><em>已完成</em></li>)}</ol>
    <p className="monitor-muted">只显示已观测的执行节点；未经过的规划阶段不会出现在此链路。</p>
  </section>;
}

export function AgentMonitor({ client = api, intervalMs = 2000 }: { client?: MonitorClient; intervalMs?: number }) {
  const [params, setParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState(params.get("run") ?? "");
  const [tripId, setTripId] = useState(params.get("trip") ?? "");
  const [follow, setFollow] = useState(!params.get("run"));
  const [runs, setRuns] = useState<MonitorRun[]>([]);
  const [tripOptions, setTripOptions] = useState<Array<{ id: string; title: string }>>([]);
  const [trace, setTrace] = useState<MonitorTrace | null>(null);
  const [stageId, setStageId] = useState("message");
  const [toolId, setToolId] = useState<string | null>(null);
  const [presentation, setPresentation] = useState(false);
  const [paired, setPaired] = useState(params.get("split") !== "0");
  const [workspaceTrip, setWorkspaceTrip] = useState(params.get("trip") ?? "");
  const [autoStage, setAutoStage] = useState(true);
  const [dialogue, setDialogue] = useState<DialogueObservation | null>(null);
  const [dialogueTrace, setDialogueTrace] = useState<DialogueTrace | null>(null);
  const [dialogueError, setDialogueError] = useState<string | null>(null);
  const activeRequest = useRef<string | null>(null);
  const activeStageElement = useRef<HTMLButtonElement | null>(null);
  const eventEnd = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncedAt, setSyncedAt] = useState<string | null>(null);
  useEffect(() => {
    if (!client.trips) return;
    const controller = new AbortController();
    void client.trips(controller.signal).then((items) => { if (!controller.signal.aborted) setTripOptions(items); }).catch(() => {});
    return () => controller.abort();
  }, [client]);
  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel(MONITOR_CHANNEL);
    channel.onmessage = (message: MessageEvent<DialogueObservation>) => {
      const event = message.data;
      if (!follow || !event || typeof event.requestId !== "string") return;
      if (event.type === "trip_selected") {
        const nextTrip = event.tripId ?? "";
        setWorkspaceTrip(nextTrip);
        if (nextTrip !== tripId) {
          activeRequest.current = null; setDialogue(null); setDialogueTrace(null); setDialogueError(null);
          setTripId(nextTrip); setTrace(null); setSelectedId("");
        }
        return;
      }
      if (event.type === "request_started") {
        activeRequest.current = event.requestId;
        setDialogue(event); setDialogueTrace(null); setDialogueError(null); setTrace(null); setSelectedId(""); setToolId(null); setAutoStage(true);
        if (event.tripId) setTripId(event.tripId);
      } else if (activeRequest.current === event.requestId) {
        setDialogue((current) => current?.requestId === event.requestId ? { ...current, ...event, at: current.at } : current);
        if (event.type === "request_completed" && event.runId) {
          if (event.tripId) setTripId(event.tripId);
          setSelectedId(event.runId); setStageId("message");
        }
      }
    };
    return () => channel.close();
  }, [follow, tripId]);
  useEffect(() => {
    if (!follow || !dialogue?.sessionId || !dialogue.messageId || !client.dialogue) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function refreshDialogue() {
      try {
        const next = await client.dialogue!(dialogue!.sessionId!, dialogue!.messageId!, controller.signal);
        if (!alive) return;
        setDialogueTrace(next); setDialogueError(null);
        if (next.status === "completed" || next.status === "failed") return;
        if (next.status === "unavailable" && dialogue?.type !== "request_started") return;
      } catch {
        if (alive) setDialogueError("阶段观测暂时不可用，正在重试；对话仍继续执行。");
      }
      if (alive) timer = setTimeout(() => void refreshDialogue(), intervalMs);
    }
    void refreshDialogue();
    return () => { alive = false; controller.abort(); clearTimeout(timer); };
  }, [client, follow, intervalMs, dialogue?.requestId, dialogue?.sessionId, dialogue?.messageId, dialogue?.type]);
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function refresh() {
      try {
        const recent = await client.runs(tripId, controller.signal);
        if (!alive) return;
        setRuns(recent);
        if (follow && dialogue && (dialogue.type === "request_started" || !dialogue.runId)) { setError(null); return; }
        const id = follow ? dialogue?.runId ?? recent[0]?.id ?? "" : selectedId || recent[0]?.id || "";
        if (id !== selectedId) {
          setTrace(null); setToolId(null); setSelectedId(id);
          return;
        }
        if (id) {
          const next = await client.trace(id, controller.signal);
          if (!alive) return;
          setTrace(next); setSyncedAt(new Date().toISOString());
          if (autoStage && follow) {
            const current = next.stages.find((stage) => stage.id === next.active_stage && stage.status === "running") ?? next.stages.find((stage) => stage.status === "running") ?? next.stages.find((stage) => stage.status === "failed") ?? next.stages.filter((stage) => stage.status === "completed").at(-1);
            if (current) { setStageId(current.id); setToolId(null); }
          }
        }
        setError(null);
      } catch (cause) {
        if (alive) setError(cause instanceof Error ? cause.message : "监控请求失败");
      } finally {
        if (alive) { setLoading(false); timer = setTimeout(() => void refresh(), intervalMs); }
      }
    }
    void refresh();
    return () => { alive = false; controller.abort(); clearTimeout(timer); };
  }, [client, follow, intervalMs, autoStage, dialogue, selectedId, tripId]);
  const stage = trace?.stages.find((item) => item.id === stageId) ?? trace?.stages[0];
  const tool = trace?.tools.find((item) => item.id === toolId);
  useEffect(() => {
    if (follow && autoStage) {
      activeStageElement.current?.scrollIntoView?.({ block: "nearest" });
      eventEnd.current?.scrollIntoView?.({ block: "nearest" });
    }
  }, [follow, autoStage, stage?.id, trace?.events.length, dialogueTrace?.events.length]);
  const selectRun = (id: string) => { setFollow(false); setDialogue(null); setTrace(null); setToolId(null); setSelectedId(id); setParams({ ...(id ? { run: id } : {}), ...(tripId ? { trip: tripId } : {}), ...(!paired ? { split: "0" } : {}) }); };
  const duration = trace?.run.started_at ? Math.max(0, (new Date(trace.run.planning_finished_at ?? trace.run.completed_at ?? syncedAt ?? Date.now()).getTime() - new Date(trace.run.started_at).getTime()) / 1000).toFixed(1) : null;
  const trips = Array.from(new Map([...tripOptions.map((trip) => [trip.id, trip.title] as const), ...runs.map((run) => [run.trip_id, run.trip_title] as const)]).entries());
  const requestStatus = trace?.run.status === "failed" ? "本次规划执行失败，已保留真实阶段与错误记录。"
    : trace?.run.status === "awaiting_confirmation" ? "候选方案已生成，等待你在左侧接受或拒绝。"
    : trace?.run.status === "accepted" ? "方案已接受，正式行程已更新。"
    : trace?.run.status === "rejected" ? "方案已拒绝，正式行程保留原有安排。"
    : "已关联实际 Agent 运行，正在同步执行阶段。";
  return <div className={paired ? "monitor-split-shell" : "monitor-single-shell"}>{paired && <aside className="monitor-conversation-frame"><iframe title="旅行总管实时对话" src={`/dev/agent-conversation${workspaceTrip ? `/${encodeURIComponent(workspaceTrip)}` : ""}`} /></aside>}<main className={`agent-monitor ${paired ? "monitor-paired" : ""} ${presentation ? "monitor-presentation" : ""}`}>
    <header className="monitor-header"><div><span className="monitor-eyebrow">ROAMSYNC · Agent 运行控制台</span><h1>RoamSync Agent 运行监控</h1><p>观察一句旅行请求如何成为可执行、经过验证的行程方案。</p></div><div className="monitor-actions"><button type="button" aria-pressed={paired} onClick={() => setPaired(!paired)}>{paired ? "独立监控" : "并排对照"}</button>{!presentation && <Link to="/trips">打开旅行工作台 ↗</Link>}<button type="button" aria-pressed={presentation} onClick={() => { setPresentation(!presentation); if (!presentation) setAutoStage(true); }}>{presentation ? "退出演示模式" : "演示模式"}</button><button type="button" onClick={() => { if (!document.fullscreenElement) void document.documentElement.requestFullscreen?.().catch(() => setError("浏览器未允许全屏，请按 F11")); else void document.exitFullscreen?.(); }}>全屏</button></div></header>
    <nav className="monitor-boundary" aria-label="系统边界">{["用户", "Agent · 理解与决策", "上下文 / tool", "规划 · 候选方案", "确定性验证", "候选行程版本", "用户确认"].map((title) => <span key={title}>{title}</span>)}</nav>
    <div className="monitor-controls"><label>历史运行 <select aria-label="历史运行" value={selectedId} onChange={(event) => selectRun(event.target.value)}><option value="">选择真实运行</option>{selectedId && !runs.some((run) => run.id === selectedId) && <option value={selectedId}>{selectedId.slice(0, 8)} · 历史运行</option>}{runs.map((run) => <option key={run.id} value={run.id}>{run.id.slice(0, 8)} · {label(run.status)} · {run.trip_title} · {clock(run.created_at)}</option>)}</select></label><label><input type="checkbox" checked={follow} onChange={(event) => { setFollow(event.target.checked); setDialogue(null); if (event.target.checked) setParams({ ...(tripId ? { trip: tripId } : {}), ...(!paired ? { split: "0" } : {}) }); }} />跟随最新运行</label><label><input type="checkbox" checked={autoStage} onChange={(event) => setAutoStage(event.target.checked)} />自动跟随阶段</label><label>旅行 <select aria-label="旅行筛选" value={tripId} onChange={(event) => { setDialogue(null); setDialogueTrace(null); if (event.target.value) setWorkspaceTrip(event.target.value); setTripId(event.target.value); setSelectedId(""); setTrace(null); setToolId(null); setFollow(true); }}><option value="">全部旅行</option>{tripId && !trips.some(([id]) => id === tripId) && <option value={tripId}>{tripId}</option>}{trips.map(([id, title]) => <option value={id} key={id}>{title}</option>)}</select></label><span className="monitor-live-label">{follow ? "◉ 实时跟随 · 轮询更新" : "↶ 历史回放"} · {clock(syncedAt)}</span></div>
    {error && <div className="monitor-error" role="alert">{error} · {trace ? "保留上次结果，正在重试。" : "正在重试。可取消跟随，选择历史运行。"}</div>}
    {trace?.error && <div className="monitor-error" role="status">× {trace.error.code} · 失败阶段：{stageTitles[trace.error.stage ?? ""] ?? "不可用"} · {trace.error.message}</div>}
    {dialogue && <section className="monitor-dialogue-observation" aria-label="实时对话请求"><span className="monitor-eyebrow">{clock(dialogue.at)} · 当前对话请求</span><strong>{dialogue.message}</strong><p aria-live="polite">{dialogue.type === "request_started" ? dialogueTrace?.events.length ? "Agent 正在处理这条对话，执行阶段持续更新。" : "请求已发送，正在等待 Agent 分流与运行记录。具体内部阶段尚未返回。" : dialogue.type === "request_failed" ? `请求失败：${dialogue.error}` : dialogue.runId ? requestStatus : "本次对话已返回；未创建新的规划运行。"}</p>{dialogueError && <small>{dialogueError}</small>}{!dialogue.runId && dialogue.assistant && <details className="monitor-answer"><summary>查看本次回答</summary><p>{dialogue.assistant}</p></details>}</section>}
    {dialogue && !trace && <DialogueExecution trace={dialogueTrace} fallback={dialogue.runtimeTrace} follow={follow} autoStage={autoStage} />}
    {trace ? <><section className="monitor-overview" aria-label="运行概览">{Object.entries({ 运行编号: `#${trace.run.id.slice(0, 8)}`, 状态: label(trace.run.status), 意图: label(trace.run.intent), 旅行: trace.run.trip_title, 行程版本: `${trace.run.base_trip_version}（规划时）· ${trace.run.current_trip_version}（当前）`, 模型: trace.run.model ?? "不可用", 开始时间: clock(trace.run.started_at), 执行耗时: duration == null ? "不可用" : `${duration} 秒` }).map(([key, value]) => <div key={key}><small>{key}</small><strong className={key === "状态" ? `status-${trace.run.status}` : ""}>{value}</strong></div>)}</section>
      <div className="monitor-workspace"><aside className="monitor-timeline"><h2>Agent 执行时间线</h2><div>{trace.stages.map((item) => <button type="button" key={item.id} ref={!toolId && stage?.id === item.id ? activeStageElement : undefined} data-status={item.status} aria-pressed={!toolId && stage?.id === item.id} onClick={() => { setAutoStage(false); setStageId(item.id); setToolId(null); }}><span className={`monitor-symbol stage-${item.status}`}>{symbols[item.status] ?? "—"}</span><span><strong>{stageTitle(item)}</strong><small>{clock(item.started_at)} · {latency(item.duration_ms)}</small><em>{stageStatus(item)}{item.attempts > 1 ? ` · ${item.attempts} 次执行` : ""}</em></span></button>)}</div></aside>
      <section className="monitor-detail" key={`${trace.run.id}:${toolId ?? stage?.id}:${presentation}`} aria-label="步骤详情"><div className="monitor-detail-heading"><span className="monitor-eyebrow">{tool ? "tool 调用" : "步骤详情"}</span><h2>{tool ? `${tool.provider ?? "服务商未记录"} · ${label(tool.purpose ?? tool.stage)}` : stage && stageTitle(stage)}</h2><span className={`monitor-badge stage-${tool?.status ?? stage?.status}`}>{tool ? label(tool.status) : stage && stageStatus(stage)}</span></div>{tool ? <><Fields value={{ 调用目的: label(tool.purpose), 服务商: tool.provider, 耗时: latency(tool.duration_ms), 状态: label(tool.status), 开始时间: clock(tool.started_at) }} /><h3>输入摘要</h3><Structured value={tool.input} /><h3>输出摘要</h3><Structured value={tool.output} /><JsonDetail title="开发者详情" value={tool} presentation={presentation} /></> : stage && <><p className="monitor-explanation">{explanations[stage.id]}</p><small className="monitor-muted">来源：{label(stage.source)} · 未保存的数据标记为不可用</small>{stage.status === "skipped" && <div className="monitor-empty">↷ 本次路径未执行此阶段。</div>}{stage.status === "unavailable" && <p className="monitor-muted">本次运行没有可用的阶段记录。</p>}{stage.data.error != null && <div className="monitor-error"><Structured value={stage.data.error} /></div>}<StageDetail stage={stage} presentation={presentation} /></>}</section>
      <aside className="monitor-tools"><section className="monitor-event-feed" aria-label={follow ? "实时事件流" : "历史事件流"}><h3>{follow ? "实时事件流" : "历史事件流"}</h3>{trace.events.slice(-18).map((event, index) => <button type="button" key={String(event.sequence ?? index)} onClick={() => { setAutoStage(false); setStageId(event.stage === "search" || event.stage === "weather" || event.stage === "research_decision" ? "research" : event.stage === "goal_check" ? "validator" : String(event.stage)); setToolId(null); }}><time>{clock(String(event.at))}</time><span className={`stage-${String(event.status)}`}>{symbols[String(event.status)] ?? "—"} {stageTitles[String(event.stage)] ?? fieldLabel(String(event.stage))}</span><small>{label(event.status)}</small></button>)}<div ref={eventEnd} /></section><h2>tool 调用</h2><p className="monitor-muted">实际调用与步骤范围</p>{trace.tools.length ? trace.tools.map((item) => <button type="button" aria-pressed={toolId === item.id} key={item.id} onClick={() => { setAutoStage(false); setToolId(item.id); }}><strong>{item.provider ?? stageTitles[item.stage] ?? fieldLabel(item.stage)}</strong><span>{label(item.purpose ?? item.stage)}</span><small className={`stage-${item.status}`}>{label(item.status)} · {latency(item.duration_ms)}</small></button>) : <p className="monitor-muted">历史运行未保存逐次 tool 调用。可查看目的地研究与路线节点中的真实结果。</p>}{trace.limitations.map((item) => <p className="monitor-muted" key={item}>{label(item)}</p>)}{trace.observations_truncated && <p className="monitor-error">超过 240 条观测事件，仅保留最近事件。</p>}{!presentation && <details className="monitor-json"><summary>开发者事件 · {trace.events.length}</summary><pre>{JSON.stringify(trace.events, null, 2)}</pre></details>}</aside></div></> : !dialogue && <section className="monitor-empty" role="status"><h2>{loading ? "正在读取真实 Agent 运行记录…" : "暂无可展示的 Agent 运行记录"}</h2><p>在正常 RoamSync 旅行工作台发送规划请求，这里会自动跟踪最新运行。历史数据读取自 PostgreSQL。</p><Link to="/trips">打开旅行工作台</Link></section>}
  </main></div>;
}
