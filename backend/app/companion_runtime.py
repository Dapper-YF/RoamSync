"""One synchronous Companion turn; durable interaction state lives in session JSON."""
from app.companion_contracts import CompanionContext, CompanionProvider, ContextReaderPort, KnowledgeToolPort, InformationNeed
from app.companion_graph import build_companion_graph
from app.companion_provider import ModelCompanionProvider
from app.schemas import TravelGoalRouting
from app.companion_facts import FactToolPort


class CompanionRuntime:
    def __init__(self, reader: ContextReaderPort, provider: CompanionProvider | None = None,
                 knowledge_tool: KnowledgeToolPort | None = None, fact_tool: FactToolPort | None = None,
                 *, knowledge_strategy: str | None = None, approved_need: InformationNeed | None = None):
        from app.config import get_settings
        strategy = knowledge_strategy or get_settings().companion_knowledge_strategy
        if strategy not in {"selective", "general_only", "forced_rag"}:
            raise ValueError("unsupported Companion knowledge strategy")
        self.graph = build_companion_graph(reader, provider or ModelCompanionProvider(), knowledge_tool, fact_tool, strategy,
            approved_need=approved_need)

    async def run(self, *, session_id: str, turn_id: str, message: str,
                  goal: TravelGoalRouting, messages: list[dict], assistant_context: dict | None = None, place_context: list[dict] | None = None, read_tool_context: dict | None = None):
        context = CompanionContext(current_message=message, travel_goal=goal,
            assistant_context=assistant_context, place_context=place_context or [], read_tool_context=read_tool_context or {},
            recent_turns=[{"id": str(m.get("id", "legacy")), "user": str(m.get("user", ""))[:4000],
                          "assistant": str(m.get("assistant", ""))[:3000]} for m in messages[-12:]])
        state = await self.graph.ainvoke({"session_id": session_id, "turn_id": turn_id,
            "messages": messages, "context": context}, config={"recursion_limit": 16})
        return state["result"]
