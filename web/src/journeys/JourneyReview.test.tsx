import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {JourneyReview} from './JourneyReview';
import type {Activity,DayPlan,PlanRevision} from '../domain/types';
const activity={id:'a',placeId:'p',name:'人民公园',scheduledTime:'13:00',durationMinutes:60,coordinates:[104,30]} as unknown as Activity;
const days=[{id:'d1',date:'2026-11-02',activities:[]},{id:'d2',date:'2026-11-03',activities:[activity]}] as DayPlan[];
const revision={id:'r',planningRunId:'run',planningGoals:{targetDays:['2026-11-03']},reason:'避开中午，下午慢慢逛。',activities:[{candidateId:'c',replacesActivityId:'a',placeCandidateId:'p',dayDate:'2026-11-03',plannedStartTime:'14:00',durationMinutes:45}]} as PlanRevision;
afterEach(cleanup);
function mount(options:Partial<React.ComponentProps<typeof JourneyReview>>={}){
 const actions={onDay:vi.fn(),onAccept:vi.fn(),onContinue:vi.fn(),onClose:vi.fn(),onReject:vi.fn()};
 render(<JourneyReview days={days} items={[]} revision={revision} places={[]} protectedIds={[]} stale={false} unverified={false} busy={false} {...actions} {...options}/>);return actions;
}
it('exposes before/after and unaffected dates before an explicit acceptance',()=>{
 const actions=mount();expect(screen.getByText('13:00 · 60分钟 → 14:00 · 45分钟')).toBeVisible();expect(screen.getByText(/范围外日期保持原样：11-02/)).toBeVisible();
 fireEvent.click(screen.getByRole('button',{name:'继续商量'}));expect(actions.onContinue).toHaveBeenCalledOnce();expect(actions.onReject).not.toHaveBeenCalled();expect(actions.onAccept).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'返回原安排'}));expect(actions.onClose).toHaveBeenCalledOnce();expect(actions.onReject).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'采用11-03的调整'}));expect(actions.onAccept).toHaveBeenCalledOnce();
});
it.each([{stale:true},{unverified:true},{revision:{...revision,activities:[{...revision.activities[0],dayDate:'2026-11-09'}]}}])('blocks adoption when the displayed scope or version cannot be trusted: %j',options=>{
 mount(options);expect(screen.getByRole('button',{name:/^采用/})).toBeDisabled();expect(screen.getByRole('alert')).toBeVisible();
});
