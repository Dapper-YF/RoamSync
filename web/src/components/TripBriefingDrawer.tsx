import { BedDouble, CalendarCheck, CloudSun, Hotel, Ticket, TrainFront, X } from "lucide-react";
import type { Trip } from "../domain/types";
import { formatFen } from "../utils/planner";

export function TripBriefingDrawer({ open, trip, onClose }: { open: boolean; trip: Trip; onClose: () => void }) {
  if (!open) return null;
  return <div className="drawer-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <aside className="briefing-drawer" aria-label="旅行总览与预订预览">
      <header><div><span className="eyebrow">TRIP READY CENTER</span><h2>旅行总览</h2><p>把行程之外的住宿、交通和出发准备集中到一个视图。</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="关闭旅行总览"><X size={18} /></button></header>
      <div className="readiness"><CalendarCheck size={21} /><span><strong>展示准备度 86%</strong><small>核心行程与路线已完成，票务和酒店为产品预览</small></span></div>
      <section className="brief-card hotel-card"><div className="brief-icon"><Hotel size={20} /></div><div className="brief-copy"><span className="preview-label">产品预览 · 未创建真实订单</span><h3>{trip.accommodation || "住宿待选择"}</h3><p>{trip.accommodationAddress || "湖滨核心区，步行可达西湖"}</p><div className="booking-facts"><span><BedDouble size={14} />湖景大床房 · 1晚</span><span>9月5日 14:00入住</span><span>9月6日 12:00退房</span></div><footer><strong>¥1,480</strong><button type="button" disabled>接入供应商后可预订</button></footer></div></section>
      <section className="brief-card"><div className="brief-icon"><TrainFront size={20} /></div><div className="brief-copy"><span className="preview-label">交通方案预览</span><h3>G7311 · 上海虹桥 → 杭州东</h3><p>07:38 出发 · 08:23 到达 · 二等座</p><footer><strong>¥73 / 人</strong><button type="button" disabled>待接入票务</button></footer></div></section>
      <section className="weather-strip"><CloudSun size={22} /><span><strong>23–29°C · 多云转晴</strong><small>展示预测；正式版将接入逐小时天气和恶劣天气重排</small></span></section>
      <section className="checklist"><h3><Ticket size={17} />预约与出发清单</h3><label><input type="checkbox" defaultChecked />杭州君悦酒店住宿信息已确认</label><label><input type="checkbox" />灵隐飞来峰实名预约</label><label><input type="checkbox" />中国茶叶博物馆预约</label><label><input type="checkbox" />返程车次与行李寄存确认</label></section>
      <section className="budget-preview"><h3>全场景预算预览</h3><div><span>住宿</span><strong>{formatFen(148_000)}</strong></div><div><span>城际交通（2人往返）</span><strong>{formatFen(29_200)}</strong></div><div><span>活动、门票与餐饮</span><strong>{formatFen(46_000)}</strong></div><div className="budget-total"><span>预计合计</span><strong>{formatFen(223_200)} / {formatFen(trip.totalBudgetFen)}</strong></div><small>该预览尚未计入实际消费账本，不会与规划预算重复计算。</small></section>
    </aside>
  </div>;
}
