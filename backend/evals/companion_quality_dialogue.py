"""Real longitudinal conversation and pure PlanningBrief handoff, no database."""
import asyncio
import json
from pathlib import Path
from time import perf_counter

from app.companion_knowledge import build_reviewed_knowledge_tool
from app.companion_provider import ModelCompanionProvider
from app.companion_runtime import CompanionRuntime
from app.companion_state import build_planning_brief
from app.travel_goal_router import route_travel_goal
from evals.companion_knowledge_strategy import MODES, CountingTool, Reader
from evals.companion_provider_smoke import failure_details

TURNS = ["我想先了解南京的文化特色，暂时不做行程。",
    "我喜欢安静的街巷和历史文化，不喜欢排队，想慢慢体验。",
    "苏州和南京哪个更适合我这种慢节奏旅行？先比较，不要规划。",
    "帮我规划南京三天行程，优先历史文化和安静街巷。"]


async def run(output):
    report = {"real": True, "database_used": False, "formal_planning_executed": False,
        "turn_inputs": TURNS, "rows": [], "complete": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    tool = await build_reviewed_knowledge_tool()
    for mode, strategy in MODES.items():
        history = []
        for index, text in enumerate(TURNS):
            goal = route_travel_goal(text, history)
            tid = f"dialogue-{index}"
            provider, counted = ModelCompanionProvider(), CountingTool(tool)
            start = perf_counter()
            row = {"mode":mode, "turn":index, "input":text, "history":list(history), "goal":goal.model_dump(mode="json")}
            try:
                if index == 3:
                    brief = build_planning_brief("quality-dialogue", tid, text, goal, history)
                    row.update(planning_brief=brief.model_dump(mode="json") if brief else None,
                        checks={"planning_routed":goal.target_runtime == "planning" and goal.mutation_requested,
                            "brief_prepared":brief is not None and brief.status == "prepared",
                            "destination":brief is not None and brief.destination == "南京",
                            "preference_preserved":brief is not None and bool(brief.confirmed_preferences),
                            "no_companion_model":not provider.observations})
                else:
                    result = await CompanionRuntime(Reader(),provider,counted,knowledge_strategy=strategy).run(
                        session_id="quality-dialogue",turn_id=tid,message=text,goal=goal,messages=history)
                    row.update(output=result.model_dump(mode="json"),
                        checks={"companion_routed":goal.target_runtime == "companion" and not goal.mutation_requested,
                            "no_handoff":result.planning_handoff is None})
                    history.append({"id":tid,"user":text,"assistant":result.response_text,
                        "goal_routing":goal.model_dump(mode="json"),"companion_result":result.model_dump(mode="json")})
            except Exception as exc:
                row.update(error=failure_details(exc))
            row.update(latency_seconds=perf_counter()-start,rag_calls=counted.calls,observations=provider.observations)
            report["rows"].append(row)
            output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            print(mode,index,"error="+str(row.get("error")),flush=True)
            if "error" in row:
                return report
    report["complete"] = True
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return report


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True,type=Path)
    asyncio.run(run(parser.parse_args().output))
