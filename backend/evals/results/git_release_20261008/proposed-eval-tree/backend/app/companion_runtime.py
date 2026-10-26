"""One synchronous Companion turn; durable interaction state lives in session JSON."""
from app.companion_contracts import CompanionContext, CompanionProvider, ContextReaderPort, KnowledgeToolPort
from app.companion_graph import build_companion_graph
from app.companion_provider import ModelCompanionProvider
from app.schemas import TravelGoalRouting
from app.companion_facts import FactToolPort


class CompanionRuntime:
    def __init__(self, reader: ContextReaderPort, provider: CompanionProvider | None = None,
                 knowledge_tool: KnowledgeToolPort | None = None, fact_tool: FactToolPort | None = None):
        self.graph = build_companion_graph(reader, provider or ModelCompanionProvider(), knowledge_tool, fact_tool)

    async def run(self, *, session_id: str, turn_id: str, message: str,
                  goal: TravelGoalRouting, messages: list[dict]):
        context = CompanionContext(current_message=message, travel_goal=goal,
            recent_turns=[{"id": str(m.get("id", "legacy")), "user": str(m.get("user", ""))[:4000],
                          "assistant": str(m.get("assistant", ""))[:3000]} for m in messages[-12:]])
        state = await self.graph.ainvoke({"session_id": session_id, "turn_id": turn_id,
            "messages": messages, "context": context}, config={"recursion_limit": 16})
        return state["result"]
