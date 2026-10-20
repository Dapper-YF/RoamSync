"""Synthetic prompts, actual assistant/service/model/providers; isolated SQL only.

No judge model, mocked evidence or private reasoning is recorded. Every request,
including failures, is retained. A run never retries to cherry-pick good answers.
"""
import asyncio
import json
from pathlib import Path
import sys
import time
import uuid
import quality_runtime
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from app.config import get_settings
from app.database import AssistantSession
from app.assistant_service import send_message
from app.assistant_places import ContentServicePlaces
from app.place_content.provider import AMapContentProvider
from app.place_content.repository import ContentRepository
from app.place_content.service import PlaceContentService

CASES = [
 ('湖边慢逛',['南京玄武湖值得去吗？我想慢慢散步。','我只有一个小时，不想走很多路。','所以适合我吗？简单说，别给我景区简介。']),
 ('吃饭与城市承接',['想吃火锅了。','成都哪家好吃？找两三家具体分店。','我不太能吃辣，人均一百左右，有适合的吗？']),
 ('具体分店比较',['成都六公里老火锅(玉林店)和皇城老妈火锅(皇城店)怎么选？','哪家差评更多？请说你实际查到了什么。','那现在谁家不用排队？不知道就直说。']),
 ('人文与景点选择',['第一次去南京，南京博物院和玄武湖有什么不同？','我更喜欢历史，但只有两小时，你会选哪个？','南京博物院这周六能直接进去吗？需要预约吗？']),
 ('城市文化自由咨询',['成都为什么有那么多茶馆？','鹤鸣茶社是游客打卡的地方，还是当地人也去？','我不想只拍照发朋友圈，想真正坐下来感受一下。']),
 ('摄影与地点检索',['成都有哪些适合拍街头生活的地方？只说两个。','玉林路和宽窄巷子，你更建议我去哪？','帮我看看玉林路的真实图片。']),
 ('位置不明确',['附近有什么好吃的？','我说的是成都人民公园附近。','只想吃早餐，一个人，不想吃火锅。']),
 ('轻量安排讨论',['我11月7日到8日在南京玩两天，想去南京博物院和玄武湖，别排太满，先聊聊。','周六下午给我留空，别把留白当成还没安排。','暂时不保存，也不用生成详细时间表，告诉我大方向就好。']),
 ('现实变化与未确认安排',['我本来今天想去玄武湖，现在累了不想走。','我没有保存过行程，只是在跟你讨论。','那就先不去了，下午留空吧。']),
 ('风格与不确定性',['大理古城值得逛吗？我不喜欢同质化商业街。','那洱海骑电动车，有什么限制要提前查？','不知道限制时，别替我说一定能骑，告诉我去哪里核实。']),
]

async def main():
    settings=get_settings()
    assert settings.database_url.endswith('/roamsync_quality_live_test') and '127.0.0.1:51422' in settings.database_url
    baseline='--baseline' in sys.argv
    recheck='--recheck' in sys.argv
    final='--final' in sys.argv
    safety='--safety' in sys.argv
    cases=[('安全保护复验',['南京博物院和玄武湖怎么选？我只有两小时，喜欢历史。'])] if safety else [('最后比较复验',['第一次去南京，南京博物院和玄武湖怎么选？我偏爱历史，只有两小时。'])] if final else [CASES[0],CASES[1]] if baseline else [CASES[i] for i in (0,3,6,8)] if recheck else CASES
    folder=Path(__file__).resolve().parents[2]/'docs/evidence/conversation-quality-20261020'
    folder.mkdir(parents=True,exist_ok=True)
    output=folder/('safety-1.json' if safety else 'final-1.json' if final else 'baseline-6.json' if baseline else 'recheck-12.json' if recheck else 'conversations-30.json')
    engine=create_async_engine(settings.database_url,poolclass=NullPool)
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    port=ContentServicePlaces(PlaceContentService(AMapContentProvider(settings.amap_rest_key),ContentRepository(create_engine(settings.database_url))),owner='quality-synthetic-user')
    records=[]
    try:
        for case_id,(name,questions) in enumerate(cases,1):
            async with sessions() as db:
                row=AssistantSession(messages=[],applied_actions={})
                db.add(row);await db.commit();sid=row.id
            for turn,question in enumerate(questions,1):
                start=time.monotonic()
                record={'case':case_id,'scenario':name,'turn':turn,'user':question}
                try:
                    async with sessions() as db:
                        row=await asyncio.wait_for(send_message(db,sid,question,uuid.uuid4(),context={},place_port=port),timeout=180)
                        result=row.messages[-1]
                        record.update(assistant=result.get('assistant',''),public_process=result.get('companion_result',{}).get('analysis_summary',''),
                            sources=result.get('read_tools',{}).get('web_search',{}),places=[c['place'] for c in result.get('place_cards',[])],tool=result.get('tool'),trip_id=str(row.trip_id) if row.trip_id else None,
                            pending_action=bool(row.pending_action))
                except Exception as exc:
                    record.update(error=type(exc).__name__,assistant=str(exc)[:500])
                record['seconds']=round(time.monotonic()-start,2)
                records.append(record)
                output.write_text(json.dumps(records,ensure_ascii=False,indent=2,default=str),encoding='utf8')
                print(json.dumps({'completed':len(records),'scenario':name,'error':record.get('error'),'seconds':record['seconds']},ensure_ascii=True),flush=True)
    finally:
        await engine.dispose()

if __name__=='__main__': asyncio.run(main())
