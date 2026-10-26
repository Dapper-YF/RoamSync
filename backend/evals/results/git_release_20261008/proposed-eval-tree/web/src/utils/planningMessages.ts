export function planningErrorMessage(message: string) {
  if (/provider could not be reached|planner.*unavailable|fetch failed|Failed to fetch/i.test(message)) return "暂时连不上 AI 服务，请稍后重试。已保存的行程和候选方案仍然保留。";
  if (/route_travel_time_conflict/.test(message)) return "这次安排的交通时间不足，方案未保存。请尝试减少当天地点，或要求预留更多交通时间。";
  if (/empty_initial_plan|initial_places_unavailable/.test(message)) return "暂时没有生成可用地点安排。请重试，或先添加感兴趣的地点再规划。";
  if (/candidate plan still violates constraints/.test(message)) return "暂时没有找到同时满足时间与预算的方案。请调整需求后重试，原行程仍然保留。";
  if (/quota|配额|429/i.test(message)) return "AI 或地图服务配额暂时耗尽，请稍后重试。当前正式行程不会受到影响。";
  if (/高德|地图/.test(message)) return message;
  if (/timeout|超时/i.test(message)) return "AI 规划超时，可以安全重试。之前保存的候选方案仍可从最近方案中恢复。";
  return message;
}
