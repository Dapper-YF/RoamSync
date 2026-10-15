"""Read-only real-provider smoke: no database, session writes or itinerary changes."""
import asyncio
import json
from time import monotonic

from app.companion_provider import ModelCompanionProvider
from app.companion_runtime import CompanionRuntime
from app.travel_goal_router import route_travel_goal


class Reader:
    async def load(self, context, need):
        return context


class NoRetrieval:
    async def retrieve(self, request):
        raise AssertionError("ordinary conversation unexpectedly requested retrieval")


async def main():
    history, outputs = [], []
    provider = ModelCompanionProvider()
    runtime = CompanionRuntime(Reader(), provider, NoRetrieval())
    for index, text in enumerate([
        "西湖有哪些历史文化特色？",
        "我想在杭州找一些适合摄影的活动，请给我两个有文化特色的建议。",
    ]):
        started = monotonic()
        result = await runtime.run(session_id="read-only-smoke", turn_id=str(index), message=text,
            goal=route_travel_goal(text, history), messages=history)
        assert result.status == "completed"
        assert result.information_need.general_knowledge_allowed
        assert not result.knowledge_retrieval and not result.knowledge_evidence
        assert not any(token in result.response_text for token in ["knowledge_", "资料支持：", "资料限制：", "助手的推断与建议"])
        assert result.planning_handoff is None
        if index == 1:
            assert len(result.suggestions) == 2
        outputs.append({"input": text, "seconds": round(monotonic() - started, 2),
            "result": result.model_dump(mode="json")})
        history.append({"id": str(index), "user": text, "assistant": result.response_text,
            "companion_result": result.model_dump(mode="json")})
    print(json.dumps({"provider_observations": provider.observations, "turns": outputs,
        "database_used": False, "formal_mutations": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
