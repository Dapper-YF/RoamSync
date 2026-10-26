import asyncio,json
from pathlib import Path
from datetime import datetime,UTC
from app.companion_facts import geocode_gateway
async def main():
 r={'checked_at':datetime.now(UTC).isoformat(),'probe':'actual configured geocode gateway; read-only'}
 try:
  p=await geocode_gateway('Nanjing');r.update(success=True,results=len(p.get('results',[])))
 except Exception as e:r.update(success=False,error=type(e).__name__)
 Path('/evidence/provider_recheck.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
asyncio.run(main())
