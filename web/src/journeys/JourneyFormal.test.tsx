import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiTripPlanningRepository } from "../data/apiTripPlanningRepository";
import type { Activity, ExecutionProgress, Trip } from "../domain/types";
import { JourneyPage } from "./JourneyPage";

const activity = { id: "activity-1", placeId: "place-1", name: "人民公园", scheduledTime: "09:00:00", durationMinutes: 60, estimatedCostFen: 0, coordinates: [104, 30], canSkip: true } as unknown as Activity;
beforeEach(() => {
  const prototype = ApiTripPlanningRepository.prototype;
  vi.spyOn(prototype, "getTrip").mockResolvedValue({ id: "test-trip", title: "验收旅行", destination: "成都", startDate: "2099-01-01", endDate: "2099-01-02", status: "active" } as Trip);
  vi.spyOn(prototype, "getDays").mockResolvedValue([{ id: "day-1", tripId: "test-trip", date: "2099-01-01", label: "第一天", theme: "公园", activities: [activity] }]);
  vi.spyOn(prototype, "listPlanningRuns").mockResolvedValue([]);
  vi.spyOn(prototype, "getCandidates").mockResolvedValue([]);
  vi.spyOn(prototype, "getExecutionProgress").mockResolvedValue({ tripId: "test-trip", currentActivityName: "人民公园", currentActivityExperience: { activityId: activity.id, activityExecutionId: "activity-execution", plannedDurationMinutes: 60, totalExtensionMinutes: 15 }, experienceImpact: { impactState: "absorbed", timeShiftMinutes: 15, minimumDownstreamSlackMinutes: 120 }, execution: { id: "execution-1", status: "in_progress", currentDate: "2099-01-01", currentDayPlanId: "day-1", currentActivityId: activity.id, remainingActivityCount: 1, scheduleDelayMinutes: 0, activities: [{ activityId: activity.id, dayPlanId: "day-1", status: "in_progress" }] } } as unknown as ExecutionProgress);
});
afterEach(() => { cleanup(); sessionStorage.clear(); localStorage.clear(); vi.restoreAllMocks(); });
function mount(onAskAssistant?: import('./journeyApi').JourneyPageProps['onAskAssistant']) { render(<MemoryRouter initialEntries={["/trips/test-trip"]}><Routes><Route path="/trips/:tripId" element={<JourneyPage onAskAssistant={onAskAssistant}/>} /></Routes></MemoryRouter>); }
it("the handbook binds a selected activity without opening a scheduling form",async()=>{
  const ask=vi.fn();mount(ask);
  await screen.findByRole('button',{name:'和 AI 调整这一天'});
  fireEvent.click(screen.getByRole('button',{name:'和 AI 商量'}));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({tripId:'test-trip',selectedDayId:'day-1',selectedDayDate:'2099-01-01',selectedActivityId:activity.id}));
  expect(screen.queryByLabelText('希望怎样调整')).not.toBeInTheDocument();
});
it('opens a fresh revision on its changed day and continues that date without rejecting it',async()=>{
  const api=ApiTripPlanningRepository.prototype;
  vi.spyOn(api,'getTrip').mockResolvedValue({id:'test-trip',title:'验收旅行',destination:'成都',startDate:'2099-01-01',endDate:'2099-01-02',status:'upcoming',version:1} as Trip);
  vi.spyOn(api,'getDays').mockResolvedValue([{id:'day-1',tripId:'test-trip',date:'2099-01-01',label:'第一天',theme:'',activities:[]},{id:'day-2',tripId:'test-trip',date:'2099-01-02',label:'第二天',theme:'',activities:[activity]}]);
  vi.spyOn(api,'listPlanningRuns').mockResolvedValue([{id:'run',baseTripVersion:1,status:'awaiting_confirmation'}] as never);
  vi.spyOn(api,'getPlanRevision').mockResolvedValue({id:'revision',planningRunId:'run',status:'pending',reason:'下午慢慢逛',planningGoals:{targetDays:['2099-01-02']},activities:[{candidateId:'changed',replacesActivityId:activity.id,placeCandidateId:activity.placeId,dayDate:'2099-01-02',plannedStartTime:'14:00',durationMinutes:60}]} as never);
  const ask=vi.fn();mount(ask);
  await screen.findByRole('region',{name:'调整预览'});
  await waitFor(()=>expect(screen.getByRole('tab',{name:'第2天 01-02'})).toHaveAttribute('aria-selected','true'));
  fireEvent.click(screen.getByRole('button',{name:/^继续商量$/}));
  expect(ask).toHaveBeenCalledWith(expect.objectContaining({selectedDayId:'day-2',selectedDayDate:'2099-01-02'}));
});
it("binds an explicit activity adjustment to the existing day and activity identity", async () => {
  const create = vi.spyOn(ApiTripPlanningRepository.prototype, "createPlanningRun").mockResolvedValue({ id: "run-1" } as never);
  localStorage.setItem("roamsync.handbook.enabled","false");
  mount();
  fireEvent.change(await screen.findByLabelText("具体活动"), { target: { value: activity.id } });
  fireEvent.change(screen.getByLabelText("希望怎样调整"), { target: { value: "只把这处活动延后半小时" } });
  fireEvent.click(screen.getByRole("button", { name: "准备候选方案" }));
  await waitFor(() => expect(create).toHaveBeenCalledWith("test-trip", "只把这处活动延后半小时", { runType: "replan", selectedDayId: "day-1", selectedActivityId: activity.id }));
});
it("explains absorbed stay changes without a disruption and sends an explicitly selected extension", async () => {
  const extend = vi.spyOn(ApiTripPlanningRepository.prototype, "extendStay").mockResolvedValue();
  mount();
  expect(await screen.findByRole("heading", { name: "可用缓冲仍能容纳这次停留变化" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "接下来的安排可能受影响" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("延长停留分钟"), { target: { value: "480" } });
  fireEvent.click(screen.getByRole("button", { name: "确认延长停留" }));
  await waitFor(() => expect(extend).toHaveBeenCalledWith("activity-execution", 480, expect.any(String)));
});
