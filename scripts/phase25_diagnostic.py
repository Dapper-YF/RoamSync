import asyncio,json
from pathlib import Path
from app.companion_provider import ModelCompanionProvider
from evals.phase25_final import evaluate,write,snapshot
class Probe(ModelCompanionProvider):
    async def generate(self,context,need):
        try:
            draft=await super().generate(context,need)
            write("provider_diagnostic_draft.json",{"allowed":[e.evidence_ref for e in context.knowledge_context],"draft":draft.model_dump(mode="json")})
            return draft
        except Exception as exc:
            cause=exc.__cause__
            write("provider_diagnostic_error.json",{"type":type(exc).__name__,"code":getattr(exc,"code",None),"cause_type":type(cause).__name__,"cause":str(cause)[:4000] if cause else None})
            raise
async def run():
    rows=[]
    for t in ["国庆想出去但怕一个人无聊"] * 3:
        first=json.loads((Path("evals/results/companion_phase25/final/real_model.json")).read_text())["cases"][0]
        history=[{"id":"0","user":"你好","assistant":first["result"]["response_text"],"goal_routing":first["goal"],"companion_result":first["result"]}]
        row=await evaluate(t,Probe(),history); rows.append(row); print(row["error"],flush=True)
        if row["error"]: break
    write("provider_diagnostic.json",{"snapshot":snapshot(),"cases":rows})
asyncio.run(run())
