import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Clock3, GripVertical, MapPin, Plus, Route, WalletCards } from "lucide-react";
import type { Activity, BudgetSummary, DayPlan, RouteLeg, ScheduleConflict } from "../domain/types";
import { formatFen } from "../utils/planner";

interface PlannerSidebarProps {
  days: DayPlan[];
  selectedDay: DayPlan;
  selectedActivityId: string | null;
  budget: BudgetSummary;
  routeLegs: RouteLeg[];
  conflicts: ScheduleConflict[];
  onSelectDay: (dayId: string) => void;
  onSelectActivity: (activityId: string) => void;
  onReorder: (activityIds: string[]) => void;
  onMoveActivity: (activity: Activity, targetDayId: string, targetPosition: number) => Promise<void>;
  onOpenPlaces: () => void;
}

export function PlannerSidebar(props: PlannerSidebarProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const { days, selectedDay, selectedActivityId, budget, routeLegs, conflicts } = props;

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over) return;
    const activity = selectedDay.activities.find((item) => item.id === String(active.id));
    if (!activity) return;
    if (over.data.current?.type === "day") {
      const targetDayId = String(over.data.current.dayId);
      const targetDay = days.find((day) => day.id === targetDayId);
      if (!targetDay) return;
      const targetPosition = targetDay.activities.filter((item) => item.id !== activity.id).length;
      void props.onMoveActivity(activity, targetDayId, targetPosition);
      return;
    }
    if (active.id === over.id) return;
    const ids = selectedDay.activities.map((item) => item.id);
    const from = ids.indexOf(String(active.id));
    const to = ids.indexOf(String(over.id));
    if (from >= 0 && to >= 0) props.onReorder(arrayMove(ids, from, to));
  }

  return (
    <aside className="planner-sidebar">
      <div className="sidebar-heading">
        <div><span className="eyebrow">DAY PLAN</span><h1>{selectedDay.theme}</h1></div>
        <button className="primary-icon-button" type="button" onClick={props.onOpenPlaces} aria-label="添加地点"><Plus size={20} /></button>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <div className="day-tabs" role="tablist" aria-label="旅行日期">
          {days.map((day, index) => <DayDropTab key={day.id} day={day} index={index} selected={day.id === selectedDay.id} onSelect={() => props.onSelectDay(day.id)} />)}
        </div>

        <div className={`budget-strip budget-${budget.status}`} data-testid="budget-summary">
          <div className="budget-copy"><WalletCards size={18} /><span>今日预计</span><strong>{formatFen(budget.plannedFen)}</strong><small>剩余 {formatFen(budget.remainingFen)}</small></div>
          <div className="budget-progress"><i style={{ width: `${Math.min(budget.ratio * 100, 100)}%` }} /></div>
        </div>
        {conflicts.length > 0 && <div className="schedule-warning" role="status"><strong>时间提醒</strong><span>{conflicts[0].message}</span></div>}

        <div className="timeline-scroll">
          {selectedDay.activities.length === 0 ? (
            <div className="empty-timeline"><MapPin size={28} /><strong>这一天还没有安排</strong><p>从候选地点中加入第一个节点。</p><button type="button" onClick={props.onOpenPlaces}><Plus size={16} />添加地点</button></div>
          ) : (
            <SortableContext items={selectedDay.activities.map((item) => item.id)} strategy={verticalListSortingStrategy}>
              <ol className="timeline-list">
                {selectedDay.activities.map((activity, index) => (
                  <li key={activity.id}>
                    <SortableActivity activity={activity} index={index} selected={activity.id === selectedActivityId} onSelect={() => props.onSelectActivity(activity.id)} />
                    {routeLegs[index] && <RouteConnector leg={routeLegs[index]} />}
                  </li>
                ))}
              </ol>
            </SortableContext>
          )}
        </div>
      </DndContext>

      <button className="add-place-button" type="button" onClick={props.onOpenPlaces}><Plus size={18} /> 从候选地点加入</button>
    </aside>
  );
}

function DayDropTab({ day, index, selected, onSelect }: { day: DayPlan; index: number; selected: boolean; onSelect: () => void }) {
  const { isOver, setNodeRef } = useDroppable({ id: `day-drop-${day.id}`, data: { type: "day", dayId: day.id } });
  return (
    <button ref={setNodeRef} className={`day-tab${selected ? " is-active" : ""}${isOver ? " is-drop-target" : ""}`} type="button" role="tab" aria-selected={selected} onClick={onSelect}>
      <span>{index + 1}</span><div><strong>{new Date(`${day.date}T00:00:00`).toLocaleDateString("zh-CN", { month: "short", day: "numeric" })}</strong><small>{day.label} · {day.activities.length} 项</small></div>
    </button>
  );
}

function SortableActivity({ activity, index, selected, onSelect }: { activity: Activity; index: number; selected: boolean; onSelect: () => void }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: activity.id, data: { type: "activity" } });
  const style = { transform: CSS.Transform.toString(transform), transition };
  return (
    <article ref={setNodeRef} style={style} className={`timeline-card${selected ? " is-selected" : ""}${isDragging ? " is-dragging" : ""}${activity.status === "skipped" ? " is-skipped" : ""}`}>
      <button className="drag-handle" type="button" aria-label={`拖动 ${activity.name}`} {...attributes} {...listeners}><GripVertical size={17} /></button>
      <button className="timeline-card-main" type="button" onClick={onSelect}>
        <span className="timeline-number">{index + 1}</span>
        <div className="timeline-card-content"><div className="timeline-meta"><span><Clock3 size={13} />{activity.scheduledTime}</span><span>{activity.durationMinutes} 分钟</span>{activity.scheduleLocked && <span>已锁定</span>}</div><strong>{activity.name}</strong><p><MapPin size={13} />{activity.neighborhood}</p></div>
        <span className="cost-tag">{activity.status === "skipped" ? "已跳过" : activity.estimatedCostFen === 0 ? "免费" : formatFen(activity.estimatedCostFen)}</span>
      </button>
    </article>
  );
}

function RouteConnector({ leg }: { leg: RouteLeg }) {
  const modeLabel = { walk: "步行", transit: "公交", driving: "驾车" }[leg.mode];
  return <div className="route-connector"><i /><span><Route size={12} />{modeLabel} {leg.durationMinutes} 分钟 · {leg.distanceMeters >= 1000 ? `${(leg.distanceMeters / 1000).toFixed(1)} km` : `${leg.distanceMeters} m`}{leg.isEstimated ? " · 估算" : ""}</span></div>;
}
