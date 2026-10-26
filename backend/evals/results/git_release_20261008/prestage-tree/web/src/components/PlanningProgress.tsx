import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import type { PlanningRun } from "../domain/types";

export function PlanningProgress({ run, startedAt }: { run?: PlanningRun; startedAt?: number }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const start = run?.progress?.updated_at ?? run?.createdAt;
  const seconds = Math.max(0, Math.floor((now - (start ? Date.parse(start) : startedAt ?? now)) / 1000));
  const heartbeatAge = run?.heartbeatAt ? Math.max(0, Math.floor((now - Date.parse(run.heartbeatAt)) / 1000)) : undefined;
  const message = run?.progress?.message ?? (run ? ({ queued: "任务已进入队列，等待开始…", researching: "正在准备目的地研究…", planning: "正在生成候选行程…", validating: "正在校验路线、时间与预算…" } as Record<string, string>)[run.status] : "正在回复…");
  return <div className="ai-message agent working" role="status">
    <LoaderCircle size={17} /><div><span>{message}</span><small className="ai-progress-detail">本阶段已等待 {seconds} 秒</small>
      {run && <small className="ai-progress-detail">{heartbeatAge === undefined ? "暂未收到执行心跳；页面会继续查询状态。" : heartbeatAge > 45 ? `已 ${heartbeatAge} 秒未收到任务心跳，执行可能中断，正在重新查询状态。` : "任务心跳正常；当前阶段尚未完成。"}</small>}
      {seconds >= 60 && <small className="ai-progress-detail">{run?.progress?.stage === "research_model" || run?.progress?.stage === "planning" ? "仍在等待模型返回完整结果；心跳正常不代表模型已完成。" : "这一阶段耗时较长，仍在等待服务返回；无需重复发送。"}</small>}
    </div>
  </div>;
}
