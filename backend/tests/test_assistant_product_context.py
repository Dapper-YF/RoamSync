import asyncio
from uuid import uuid4
from datetime import UTC,datetime
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app.assistant_context import ContextEnvelope,DiscoveryReadContext,restore_context
from app.assistant_places import PlaceView,ContentServicePlaces,load_places,load_read_tools,place_cards,PlaceAdviceSelection,render_place_advice
from app.drafts.contracts import DraftCreate
from app.drafts.repository import DraftRepository,metadata
from app.companion_contracts import CompanionContext,CompanionResult,InformationNeed

def place(ref,name):
 return PlaceView(place_id=ref,name=name,city='成都市',category='food',longitude=104.06,latitude=30.66,address='服务商地址',rating=4.3,reference_cost_yuan=60,source='fixture://provider',retrieved_at=datetime.now(UTC).isoformat())

class Port:
 def __init__(self,items):self.items=items;self.searches=0
 async def get_place(self,ref):return self.items.get(ref)
 async def search(self,**kw):self.searches+=1;return []

def test_comparison_resolves_exact_user_set_and_does_not_replace_with_search():
 a,b=uuid4(),uuid4();port=Port({a:place(a,'第一家'),b:place(b,'第二家')})
 context=ContextEnvelope(discussing_place_ids=[a,b,a],browsing_city='成都')
 focus,items,gaps=asyncio.run(load_places(port,context,'比较附近这两家，推荐哪个？'))
 assert focus is None and [p.place_id for p in items]==[a,b] and not gaps
 assert port.searches==0 and context.action_target is None and context.physical_location is None

def test_comparison_missing_identity_is_not_replaced_or_bound_to_wrong_id():
 a,b=uuid4(),uuid4();port=Port({a:place(a,'第一家'),b:place(uuid4(),'冒名地点')})
 _,items,gaps=asyncio.run(load_places(port,ContextEnvelope(discussing_place_ids=[a,b]),'比较它们'))
 assert [p.place_id for p in items]==[a] and gaps and port.searches==0

def test_comparison_cards_keep_real_refs_even_when_names_duplicate():
 a,b=uuid4(),uuid4();items=[place(a,'同名店'),place(b,'同名店')]
 result=CompanionResult(response_text='比较已知信息。',goal_type='comparison',status='completed',information_need=InformationNeed())
 cards=place_cards(result,items,None,[a,b])
 assert [c['place']['place_id'] for c in cards]==[str(a),str(b)]
 assert all(c['role']=='discussed' for c in cards)

def test_comparison_renders_reference_facts_not_invented_route_time():
 a,b=uuid4(),uuid4();items=[place(a,'第一家'),place(b,'第二家').model_copy(update={'rating':None,'reference_cost_yuan':None})]
 from app.travel_goal_router import route_travel_goal
 context=CompanionContext(current_message='比较这两家',travel_goal=route_travel_goal('比较这两家'),
  place_context=[p.model_dump(mode='json') for p in items],assistant_context=ContextEnvelope(discussing_place_ids=[a,b],discovery_context=DiscoveryReadContext(center={'longitude':104.06,'latitude':30.66,'coordinate_system':'gcj02'},min_rating=4,max_food_price_yuan=80)).model_dump(mode='json'))
 answer=render_place_advice(PlaceAdviceSelection(approach='compare',selected_place_names=['第一家','第二家']),context).response_text
 assert '评分4.3/5' in answer and '参考消费约60元/人' in answer and '评分暂无' in answer and '参考消费暂无' in answer
 assert '直线约0米' in answer and '不是步行距离' in answer and '半径3000米' in answer
 assert '分钟' not in answer

def test_draft_reader_uses_trusted_owner_and_marks_stale_page_version():
 engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False});metadata.create_all(engine)
 repo=DraftRepository(engine);draft=repo.create('alice',DraftCreate(city='成都',title='独立草稿'))
 port=ContentServicePlaces(None,repo,'alice')
 result=asyncio.run(load_read_tools(port,ContextEnvelope(read_draft_id=draft.id,read_draft_version=draft.version+1)))
 assert result['draft']['status']=='available' and result['draft']['page_version_matches'] is False
 assert result['draft']['result']['scope']=='server_saved_draft_readonly'
 other=asyncio.run(load_read_tools(ContentServicePlaces(None,repo,'bob'),ContextEnvelope(read_draft_id=draft.id)))
 assert other['draft']['status']=='unavailable' and 'result' not in other['draft']
 assert repo.get('alice',draft.id).version==draft.version
 engine.dispose()

def test_switching_drafts_resets_old_draft_history_without_action_authority():
 old=ContextEnvelope(read_draft_id=uuid4(),browsing_city='成都')
 incoming=ContextEnvelope(read_draft_id=uuid4(),browsing_city='成都')
 current,history=restore_context(incoming,[{'context':old.model_dump(mode='json')}])
 assert history==[] and current.action_target is None and current.physical_location is None


def test_saved_draft_and_trip_questions_do_not_launch_unrelated_poi_discovery():
 for context in [ContextEnvelope(read_draft_id=uuid4(),browsing_city='成都'),ContextEnvelope(read_trip_id=uuid4(),browsing_city='成都')]:
  port=Port({})
  focus,items,gaps=asyncio.run(load_places(port,context,'当前已保存的方案有哪些活动？'))
  assert focus is None and not items and not gaps and port.searches==0
