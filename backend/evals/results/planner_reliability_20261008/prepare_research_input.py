import asyncio,json,uuid
from pathlib import Path
from app.planning_context import build_planning_context
from app.database import session_factory
async def main():
 async with session_factory()as s:
  c=(await build_planning_context(s,uuid.UUID('5f3846c6-633c-425a-84ef-51496f488322'))).model_dump(mode='json')
  sources=json.loads(Path('/tmp/research_previous_sources.json').read_text(encoding='utf-8'))
  x={'destination':c['trip']['destination'],'days':len(c['days']),'user_request':'请根据已保存的日期、预算和旅行偏好生成完整行程。','preferences':c['preferences'],'sources':sources}
  Path('/tmp/health_research_input.json').write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'days':x['days'],'sources':len(sources),'input_chars':len(json.dumps(x,ensure_ascii=False))}))
asyncio.run(main())
