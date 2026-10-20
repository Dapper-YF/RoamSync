import asyncio
import json
from pathlib import Path
import evidence_runtime
from app.config import get_settings
from app.assistant_context import ContextEnvelope
from app.assistant_research import determine_lookup, research, structured
from app.assistant_places import ContentServicePlaces
from app.place_content.service import PlaceContentService
from app.place_content.provider import AMapContentProvider
from app.place_content.repository import ContentRepository
from sqlalchemy import create_engine

async def main():
    settings = get_settings()
    port = ContentServicePlaces(PlaceContentService(AMapContentProvider(settings.amap_rest_key), ContentRepository(create_engine(settings.database_url))))
    report = []
    for message, history in [("成都哪家好吃？帮我查两三家，比较一下。", [{"user": "想吃火锅了"}]), ("南京玄武湖值得去吗？想看看真实图片", []), ("成都六公里老火锅(玉林店)和皇城老妈火锅(皇城店)有什么区别？查一下资料", [])]:
        try:
            intent = await determine_lookup(settings, message, history, ContextEnvelope())
            async def judge(*args): return intent
            drafts = []
            async def answer(*args):
                draft = await structured(*args)
                drafts.append(draft.model_dump())
                return draft
            bundle = await research(settings, message, history, ContextEnvelope(), port, judge=judge, answer=answer)
            report.append({"message": message, "intent": intent.model_dump(), "result": bundle, "drafts": drafts})
        except Exception as exc:
            import traceback
            traceback.print_exc()
            report.append({"message": message, "error": type(exc).__name__, "message_detail": str(exc)[:500]})
    path = Path(__file__).resolve().parents[2] / "docs/evidence/evidence-assistant-20261020/live-lookup.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps([{k:v for k,v in item.items() if k != "result"} for item in report], ensure_ascii=True))

if __name__ == "__main__": asyncio.run(main())
