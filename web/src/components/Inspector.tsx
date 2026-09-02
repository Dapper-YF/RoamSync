import { Clock3, ExternalLink, LockKeyhole, MapPin, Pencil, Save, Star, Trash2, X } from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import type { Activity, ActivityUpdateInput, DayPlan } from "../domain/types";
import { formatFen } from "../utils/planner";

interface InspectorProps {
  activity: Activity | null;
  days: DayPlan[];
  currentDayId: string;
  busy: boolean;
  onClose: () => void;
  onRemove: (activityId: string) => void;
  onSave: (activityId: string, input: ActivityUpdateInput) => Promise<void>;
  onMove: (activity: Activity, targetDayId: string, targetPosition: number) => Promise<void>;
}

export function Inspector({ activity, days, currentDayId, busy, onClose, onRemove, onSave, onMove }: InspectorProps) {
  const [editing, setEditing] = useState(false);
  const [discardPrompt, setDiscardPrompt] = useState(false);
  const [customName, setCustomName] = useState("");
  const [scheduledTime, setScheduledTime] = useState("");
  const [durationMinutes, setDurationMinutes] = useState("");
  const [estimatedYuan, setEstimatedYuan] = useState("");
  const [status, setStatus] = useState<Activity["status"]>("planned");
  const [note, setNote] = useState("");
  const [scheduleLocked, setScheduleLocked] = useState(false);
  const [targetDayId, setTargetDayId] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!activity) return;
    setCustomName(activity.customName ?? "");
    setScheduledTime(activity.scheduledTime);
    setDurationMinutes(String(activity.durationMinutes));
    setEstimatedYuan(fenToInput(activity.estimatedCostFen));
    setStatus(activity.status);
    setNote(activity.note ?? "");
    setScheduleLocked(activity.scheduleLocked);
    setTargetDayId(days.find((day) => day.id !== currentDayId)?.id ?? currentDayId);
    setEditing(false);
    setDiscardPrompt(false);
    setFormError(null);
  }, [activity?.id, activity?.version, currentDayId, days, activity]);

  const dirty = useMemo(() => activity ? (
    customName.trim() !== (activity.customName ?? "")
    || scheduledTime !== activity.scheduledTime
    || durationMinutes !== String(activity.durationMinutes)
    || estimatedYuan !== fenToInput(activity.estimatedCostFen)
    || status !== activity.status
    || note.trim() !== (activity.note ?? "")
    || scheduleLocked !== activity.scheduleLocked
  ) : false, [activity, customName, scheduledTime, durationMinutes, estimatedYuan, status, note, scheduleLocked]);

  if (!activity) return null;
  const otherDays = days.filter((day) => day.id !== currentDayId);

  function requestClose() {
    if (editing && dirty) setDiscardPrompt(true);
    else onClose();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!activity) return;
    const duration = Number(durationMinutes);
    const estimatedCostFen = yuanInputToFen(estimatedYuan);
    if (!Number.isInteger(duration) || duration < 5 || duration > 1440) {
      setFormError("停留时长需要是 5–1440 分钟的整数");
      return;
    }
    if (estimatedCostFen === null) {
      setFormError("费用最多保留两位小数，且不能为负数");
      return;
    }
    setFormError(null);
    await onSave(activity.id, {
      version: activity.version,
      customName: customName.trim() || null,
      scheduledTime,
      durationMinutes: duration,
      estimatedCostFen,
      status,
      note: note.trim() || null,
      scheduleLocked,
    });
  }

  return (
    <aside className="inspector" aria-label="活动详情" data-testid="inspector">
      <div className={`inspector-hero category-${activity.category}`}>
        <button type="button" className="close-button" onClick={requestClose} aria-label="关闭详情"><X size={18} /></button>
        <span className="hero-kicker">{editing ? "EDIT ACTIVITY" : "PLANNED STOP"}</span>
        <h2>{activity.name}</h2>
        <p><MapPin size={15} />{activity.neighborhood}</p>
      </div>
      <div className="inspector-body">
        {discardPrompt && <div className="discard-prompt" role="alert"><strong>放弃未保存的修改？</strong><div><button type="button" onClick={() => setDiscardPrompt(false)}>继续编辑</button><button type="button" onClick={onClose}>放弃并关闭</button></div></div>}
        {editing ? (
          <form className="activity-form" onSubmit={(event) => void submit(event)}>
            <label><span>显示名称</span><input value={customName} maxLength={160} onChange={(event) => setCustomName(event.target.value)} placeholder={activity.originalName} /></label>
            <div className="activity-form-grid">
              <label><span>开始时间</span><input type="time" required value={scheduledTime} onChange={(event) => setScheduledTime(event.target.value)} /></label>
              <label><span>停留分钟</span><input type="number" min="5" max="1440" step="5" required value={durationMinutes} onChange={(event) => setDurationMinutes(event.target.value)} /></label>
            </div>
            <label><span>预计费用（元）</span><input inputMode="decimal" value={estimatedYuan} onChange={(event) => setEstimatedYuan(event.target.value)} /></label>
            <label><span>活动状态</span><select value={status} onChange={(event) => setStatus(event.target.value as Activity["status"])}><option value="planned">已计划</option><option value="active">进行中</option><option value="completed">已完成</option><option value="skipped">已跳过</option></select></label>
            <label><span>备注</span><textarea rows={4} maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} placeholder="门票、集合点或其他提醒" /></label>
            <label className="lock-field"><input type="checkbox" checked={scheduleLocked} onChange={(event) => setScheduleLocked(event.target.checked)} /><LockKeyhole size={15} /><span>固定开始时间，不随前序活动自动顺延</span></label>
            {formError && <p className="form-error" role="alert">{formError}</p>}
            <div className="inspector-actions"><button type="button" onClick={() => setEditing(false)} disabled={busy}>取消</button><button className="save-activity" type="submit" disabled={busy || !dirty}><Save size={15} />{busy ? "保存中" : "保存修改"}</button></div>
          </form>
        ) : (
          <>
            <div className="fact-grid">
              <div><Clock3 size={17} /><small>开始</small><strong>{activity.scheduledTime}</strong></div>
              <div><Star size={17} /><small>停留</small><strong>{activity.durationMinutes} 分钟</strong></div>
            </div>
            <button className="edit-activity-button" type="button" onClick={() => setEditing(true)}><Pencil size={15} />编辑活动</button>
            <section className="detail-section"><span className="section-label">预算预估</span><div className="large-money">{activity.estimatedCostFen === 0 ? "免费" : formatFen(activity.estimatedCostFen)}</div><p>{activity.status === "skipped" ? "该活动已跳过，不计入规划预算。" : "金额用于规划预算，实际消费仍由消费账本记录。"}</p></section>
            {activity.note && <section className="detail-section"><span className="section-label">备注</span><p className="activity-note">{activity.note}</p></section>}
            <section className="detail-section move-section"><span className="section-label">移动到其他日期</span>{otherDays.length ? <><select aria-label="移动到其他日期" value={targetDayId} onChange={(event) => setTargetDayId(event.target.value)}>{otherDays.map((day) => <option key={day.id} value={day.id}>{day.label} · {day.date}（{day.activities.length} 项）</option>)}</select><div><button type="button" disabled={busy} onClick={() => void onMove(activity, targetDayId, 0)}>移到开头</button><button type="button" disabled={busy} onClick={() => void onMove(activity, targetDayId, days.find((day) => day.id === targetDayId)?.activities.length ?? 0)}>移到末尾</button></div></> : <p>当前旅行只有一天。</p>}</section>
            <section className="detail-section source-card"><div><span className="section-label">信息来源</span><span className="confidence-badge">高可信</span></div><strong>{activity.source.title}</strong><p>{activity.source.provider} · {new Date(activity.source.queriedAt).toLocaleDateString("zh-CN")}</p><a href={activity.source.url} target="_blank" rel="noreferrer">查看原始页面 <ExternalLink size={13} /></a></section>
            <button className="danger-button" type="button" disabled={busy} onClick={() => onRemove(activity.id)}><Trash2 size={16} />移出当天行程</button>
          </>
        )}
      </div>
    </aside>
  );
}

function fenToInput(fen: number) {
  const yuan = Math.trunc(fen / 100);
  const cents = Math.abs(fen % 100);
  return cents ? `${yuan}.${String(cents).padStart(2, "0")}` : String(yuan);
}

function yuanInputToFen(value: string) {
  const normalized = value.trim();
  if (!/^\d+(?:\.\d{0,2})?$/.test(normalized)) return null;
  const [yuan, cents = ""] = normalized.split(".");
  return Number(yuan) * 100 + Number(cents.padEnd(2, "0"));
}
