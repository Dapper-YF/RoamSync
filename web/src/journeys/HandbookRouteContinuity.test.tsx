import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {MemoryRouter} from 'react-router-dom';
import type {Activity, DayPlan, Trip} from '../domain/types';
import {HandbookJourney} from './HandbookJourney';

const park:Activity={id:'park',placeId:'park-place',name:'人民公园',originalName:'人民公园',category:'sight',neighborhood:'',importance:'normal',version:1,updatedAt:'2099-11-01T00:00:00Z',source:{id:'source',title:'测试地点',url:'',provider:'test',queriedAt:'2099-11-01T00:00:00Z',confidence:'high'},scheduledTime:'10:00',durationMinutes:60,coordinates:[104.057,30.657],estimatedCostFen:0,status:'planned',scheduleLocked:true};
const lane:Activity={...park,id:'lane',placeId:'lane-place',name:'宽窄巷子',originalName:'宽窄巷子',scheduledTime:'13:30',scheduleLocked:false};
const day={id:'day',tripId:'trip',date:'2099-11-09',label:'第一天',activities:[park,lane],routeLegs:[{id:'leg',fromActivityId:park.id,toActivityId:lane.id,mode:'walk',durationMinutes:15,distanceMeters:1121,isEstimated:false,provider:'AMap Route 2.0'}]} as DayPlan;
const free={id:'lunch',kind:'free_window',label:'午饭留白',day_date:day.date,start:'12:00',end:'13:00',activity_id:null};
beforeEach(()=>{
  vi.stubGlobal('fetch',vi.fn(async(input:RequestInfo|URL)=>new Response(JSON.stringify(String(input).endsWith('/arrangement-items')?{items:[free]}:{version:1,records:[]}),{status:200,headers:{'Content-Type':'application/json'}})));
});
afterEach(()=>{cleanup();localStorage.clear();sessionStorage.clear();vi.unstubAllGlobals()});

function mount(){
  const route=vi.fn();
  render(<MemoryRouter><HandbookJourney trip={{id:'trip',title:'路线连续性',destination:'成都',startDate:day.date,endDate:day.date,version:4,status:'upcoming'} as Trip}
    days={[day]} places={[]} runs={[]} revisions={[]} selection={day.id} selectDay={vi.fn()}
    busy={false} error="" notice="" refresh={vi.fn()} perform={vi.fn()} execution={null}
    route={route} progress={null} executionAction={vi.fn()}/></MemoryRouter>);
  return route;
}

it('shows the actual route to the next place when deliberate free time lies between stops',async()=>{
  mount();
  await screen.findByRole('heading',{name:'午饭留白'});
  expect(screen.getByText('前往 宽窄巷子 · 步行 15分钟 · AMap Route 2.0')).toBeVisible();
  expect(screen.getByText('保留这段空闲，不自动补项目。')).toBeVisible();
});

it('queries the next stop from the preceding place across an unlocated free window',async()=>{
  const route=mount();
  await screen.findByRole('heading',{name:'午饭留白'});
  const stop=screen.getByRole('heading',{name:'宽窄巷子'}).closest('li')!;
  fireEvent.click(within(stop).getByRole('button',{name:'查询路线'}));
  expect(route).toHaveBeenCalledWith(lane,park);
});
