import {render,screen,within} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {expect,it,vi} from 'vitest';
import {AssistantDecisions} from './AssistantDecisions';
const state=vi.hoisted(()=>({value:{} as Record<string,unknown>}));
vi.mock('./TravelAssistant',()=>({useTravelAssistant:()=>state.value}));
it('keeps saved revision acceptance while showing only concise changed stops',()=>{
  const activities=Array.from({length:8},(_,n)=>({id:`a${n}`,place_id:`p${n}`,display_name:`地点${n}`,scheduled_time:'09:00',duration_minutes:60}));
  const proposed=activities.map((a,n)=>({candidate_id:`c${n}`,replaces_activity_id:a.id,place_candidate_id:a.place_id,day_date:'2026-11-01',planned_start_time:n===0?'10:00':'09:00',duration_minutes:60}));
  state.value={session:{pending_action:null},busy:false,arrangement:{version:3,trip:{id:'t',title:'已保存行程'},days:[{date:'2026-11-01',activities}]},run:{status:'awaiting_confirmation',base_trip_version:3},revision:{id:'r',status:'pending',reason:'只把第一站推迟一小时。',proposed_snapshot:{activities:proposed,route_legs:[]}},decideRevision:vi.fn(),closeAssistant:vi.fn()};
  render(<MemoryRouter><AssistantDecisions/></MemoryRouter>);
  const section=screen.getByRole('region',{name:'局部调整建议'});
  expect(within(section).getAllByRole('listitem')).toHaveLength(1);
  expect(within(section).getByText(/地点0/)).toHaveTextContent('原来 09:00 / 60分钟 → 10:00 / 60分钟');
  expect(within(section).queryByText(/地点1/)).toBeNull();
  expect(within(section).getByRole('button',{name:'采用这次调整'})).toBeDisabled();
  expect(within(section).getByRole('link',{name:/查看完整改动/})).toHaveAttribute('href','/trips/t');
});
