import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {HandbookPhoto} from './HandbookPhotos';

const ref={place_id:'a7ac051f-0453-5b88-985c-33d1593fa1fa',external_ref:{provider:'amap' as const,provider_place_id:'B020001R2Q'}};
const place={ref,name:'拙政园',city:'苏州市',location:{longitude:120.629,latitude:31.324}};
const image={url:'https://images.example.org/suzhou.jpg',source_url:'https://images.example.org/suzhou.jpg',description:'苏州拙政园园景',usage_basis:'search_reference'};
const response=(data:unknown)=>({ok:true,json:async()=>data}) as Response;
afterEach(()=>{cleanup();vi.unstubAllGlobals();});

it('loads a sourced reference photo for a confirmed saved place outside the reviewed catalog',async()=>{
  const fetcher=vi.fn(async(url:RequestInfo|URL)=>response(String(url).includes('/places/')?{status:'available',place,images:[image]}:{items:[]}));
  vi.stubGlobal('fetch',fetcher);
  render(<HandbookPhoto city="苏州" name="自定义的园林漫步" placeRef={ref} coordinates={[120.629,31.324]}/>);
  const img=await screen.findByRole('img',{hidden:true});
  fireEvent.load(img);
  expect(img).toBeVisible();
  expect(screen.getByText(/地点参考照片/)).toBeVisible();
  expect(fetcher.mock.calls.some(([url])=>String(url).includes(ref.place_id))).toBe(true);
  expect(screen.getByRole('link',{name:'图片来源'})).toHaveAttribute('href',image.source_url);
});

it('does not show photos returned for a different provider identity',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>response({status:'available',place:{...place,ref:{...ref,external_ref:{...ref.external_ref,provider_place_id:'OTHER'}}},images:[image]})));
  render(<HandbookPhoto city="苏州" name="拙政园" placeRef={ref}/>);
  await act(async()=>{});
  expect(screen.queryByRole('img',{hidden:true})).toBeNull();
});

it('never resolves a photo by an unbound activity title',async()=>{
  const fetcher=vi.fn(async(_url:RequestInfo|URL)=>response({items:[]}));vi.stubGlobal('fetch',fetcher);
  render(<HandbookPhoto city="未绑定地点测试" name="午餐"/>);
  await act(async()=>{});
  expect(fetcher.mock.calls.some(([url])=>String(url).includes('/places/'))).toBe(false);
  expect(screen.queryByRole('img',{hidden:true})).toBeNull();
});

it('discards an old photo response after switching to another saved activity',async()=>{
  let finish!: (response:Response)=>void;
  const otherRef={...ref,place_id:'second-canonical',external_ref:{...ref.external_ref,provider_place_id:'SECOND'}};
  const otherPlace={...place,ref:otherRef,name:'狮子林'};
  const otherImage={...image,url:'https://images.example.org/lion.jpg',description:'苏州狮子林园景'};
  const fetcher=vi.fn(async(url:RequestInfo|URL)=>{
    if(String(url).includes(ref.place_id))return new Promise<Response>(resolve=>{finish=resolve;});
    return response({status:'available',place:otherPlace,images:[otherImage]});
  });
  vi.stubGlobal('fetch',fetcher);
  const {rerender}=render(<HandbookPhoto city="苏州" name="拙政园" placeRef={ref}/>);
  await waitFor(()=>expect(finish).toBeDefined());
  rerender(<HandbookPhoto city="苏州" name="狮子林" placeRef={otherRef}/>);
  await screen.findByRole('img',{name:'苏州狮子林园景',hidden:true});
  await act(async()=>{finish(response({status:'available',place,images:[image]}));});
  expect(screen.queryByRole('img',{name:'苏州拙政园园景',hidden:true})).toBeNull();
});

it('hides a failed remote image without removing the saved activity content',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>response({status:'available',place,images:[image]})));
  render(<div><h3>拙政园 · 10:00</h3><HandbookPhoto city="苏州" name="拙政园" placeRef={ref}/></div>);
  fireEvent.error(await screen.findByRole('img',{hidden:true}));
  expect(screen.queryByRole('img',{hidden:true})).toBeNull();
  expect(screen.getByText('拙政园 · 10:00')).toBeVisible();
});
