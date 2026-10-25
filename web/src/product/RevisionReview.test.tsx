import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {RevisionReview,type RevisionReviewData} from './RevisionReview';
import {adoptReviewedRevision,arrangementAction,type Arrangement,type Revision} from './arrangementApi';
afterEach(()=>{cleanup();vi.unstubAllGlobals();});
const review:RevisionReviewData={complete:true,base_trip_version:4,changes:[{kind:'remove',before:{name:'旧馆',place_id:'old',date:'2026-11-09',time:'10:00',duration_minutes:60,estimated_cost_fen:0,locked:false},after:null}],routes:[],warnings:[{message:'园内步行资料不足'}]};
const arrangement={version:4,trip:{id:'trip'},days:[],items:[]} as unknown as Arrangement;
const revision:Revision={id:'revision',status:'pending',reason:'仅删除旧馆',proposed_snapshot:{activities:[]},validation_result:{},presentation_hash:'a'.repeat(64),review};
it('shows deleted activities and bound risk warnings',()=>{
 render(<RevisionReview review={review}/>);
 expect(screen.getByRole('listitem')).toHaveTextContent('删除：原来 旧馆');
 expect(screen.getByText('需留意：园内步行资料不足')).toBeInTheDocument();
});
it('sends passive binding on discussion and adopts via the common chat writer',async()=>{
 const fetcher=vi.fn(async(_url:string,_init?:RequestInit)=>new Response('{}'));vi.stubGlobal('fetch',fetcher);
 expect(arrangementAction('先不采用',arrangement,'mid',revision)).toMatchObject({operation:'plan_trip',revision_hash:'a'.repeat(64)});
 await adoptReviewedRevision('session',arrangement,revision,{topic_id:'same-topic'});
 expect(fetcher.mock.calls[0][0]).toBe('/api/v1/assistant/sessions/session/messages');
 const body=JSON.parse((fetcher.mock.calls as unknown as [string,RequestInit][])[0][1].body as string);
 expect(body.context).toMatchObject({topic_id:'same-topic',read_trip_id:'trip',action_target:{revision_id:'revision',revision_hash:'a'.repeat(64),expected_version:4,authorization_message_id:body.message_id}});
 expect(body.message).toBe('请采用并保存当前这份修改候选。');
});
it('does not submit an incomplete or stale displayed review',async()=>{
 const fetcher=vi.fn();vi.stubGlobal('fetch',fetcher);
 await expect(adoptReviewedRevision('s',arrangement,{...revision,review:{...review,complete:false}})).rejects.toThrow('完整修改候选');
 await expect(adoptReviewedRevision('s',{...arrangement,version:5},revision)).rejects.toThrow('完整修改候选');
 expect(fetcher).not.toHaveBeenCalled();
});
