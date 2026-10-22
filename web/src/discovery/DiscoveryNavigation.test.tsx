import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {MemoryRouter,useLocation} from 'react-router-dom';
import {DiscoveryApp} from './DiscoveryApp';
import {PlaceContentRepository} from '../data/placeContentRepository';
const json=(body:unknown)=>new Response(JSON.stringify(body));
function Location(){const l=useLocation();return <output data-testid="url">{l.pathname+l.search}</output>}
beforeEach(()=>{sessionStorage.clear();localStorage.clear();vi.stubGlobal('scrollTo',vi.fn());vi.spyOn(PlaceContentRepository.prototype,'search').mockResolvedValue({items:[],source:'高德',fetched_at:''});vi.spyOn(PlaceContentRepository.prototype,'favorites').mockResolvedValue({items:[],source:'高德',fetched_at:''});vi.stubGlobal('fetch',vi.fn(async(url:string)=>json(url.includes('/locations/cities')?[{name:'成都市'}]:{})))});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()});
it('keeps successful search in Explore and restores its URL on a fresh mount',async()=>{
 const mounted=render(<MemoryRouter initialEntries={['/explore']}><DiscoveryApp/><Location/></MemoryRouter>);
 fireEvent.change(screen.getByRole('textbox',{name:'城市或地点'}),{target:{value:'人民公园'}});fireEvent.change(screen.getByRole('textbox',{name:'所在城市'}),{target:{value:'成都'}});fireEvent.click(screen.getByRole('button',{name:/^搜索$/}));
 await waitFor(()=>expect(screen.getByTestId('url').textContent).toMatch(/^\/explore\?city=/));const url=screen.getByTestId('url').textContent!;
 expect(screen.queryByRole('textbox',{name:'告诉助手你的旅行想法'})).not.toBeInTheDocument();mounted.unmount();sessionStorage.clear();
 render(<MemoryRouter initialEntries={[url]}><DiscoveryApp/></MemoryRouter>);
 await waitFor(()=>expect(PlaceContentRepository.prototype.search).toHaveBeenCalledWith(expect.objectContaining({city:'成都市',q:'人民公园'}),expect.any(AbortSignal)));
});
it('takes both empty favorites links back to Explore',async()=>{
 render(<MemoryRouter initialEntries={['/favorites']}><DiscoveryApp/></MemoryRouter>);
 expect(await screen.findByRole('link',{name:/去探索/})).toHaveAttribute('href','/explore');expect(screen.getByRole('link',{name:'返回探索'})).toHaveAttribute('href','/explore');
});
