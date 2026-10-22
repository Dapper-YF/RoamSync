import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach,it,expect,vi} from 'vitest';
import {ApiTripPlanningRepository} from '../data/apiTripPlanningRepository';
import type {Trip} from '../domain/types';
import {SavedIntentionsPanel} from './SavedIntentionsPanel';
import {listSavedIntentions,revokeIntention,transferIntention,type SavedIntention} from './savedIntentions';
vi.mock('./savedIntentions',()=>({listSavedIntentions:vi.fn(),revokeIntention:vi.fn(),transferIntention:vi.fn()}));
const item={id:'i',source_session_id:'s',place_text:'人民公园',status:'active',version:1,captured_at:'2026-10-22T10:00:00+08:00',source_text:'记下人民公园'} as SavedIntention;
const trip={id:'t',title:'未来旅行',startDate:'2099-01-01',endDate:'2099-01-03',version:2} as Trip;
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.clearAllMocks()});
it('retains the saved item and visible error after a failed revoke and refresh',async()=>{
 vi.mocked(listSavedIntentions).mockResolvedValue([item]);vi.mocked(revokeIntention).mockRejectedValue(new Error('保存服务暂不可用'));
 render(<SavedIntentionsPanel trips={[trip]} onChanged={vi.fn()}/>);
 await waitFor(()=>expect(listSavedIntentions).toHaveBeenCalled());fireEvent.click(screen.getByText('记下的打算 · 1'));
 fireEvent.click(screen.getByRole('button',{name:'撤销这项打算'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('保存服务暂不可用');expect(screen.getByText('人民公园')).toBeInTheDocument();
});
it('does not silently transfer against a newer trip version than the visible list',async()=>{
 vi.mocked(listSavedIntentions).mockResolvedValue([item]);vi.spyOn(ApiTripPlanningRepository.prototype,'getTrip').mockResolvedValue({...trip,version:3});
 render(<SavedIntentionsPanel trips={[trip]} onChanged={vi.fn()}/>);
 await waitFor(()=>expect(listSavedIntentions).toHaveBeenCalled());fireEvent.click(screen.getByText('记下的打算 · 1'));fireEvent.click(screen.getByText('放入某趟旅行'));
 fireEvent.change(screen.getByLabelText('为人民公园选择旅行'),{target:{value:'t'}});fireEvent.click(screen.getByRole('button',{name:'作为时间未定的选择放入'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('旅行已有新修改');expect(transferIntention).not.toHaveBeenCalled();
});
