"""Composition root for the small reviewed corpus. No runtime retrieval network."""
import json
from pathlib import Path

from app.tourism_knowledge.ingestion import CuratedKnowledgeIngestor
from app.tourism_knowledge.models import KnowledgeDocument
from app.tourism_knowledge.repository import InMemoryKnowledgeRepository
from app.tourism_knowledge.service import TourismKnowledgeService
from app.tourism_knowledge_adapter import TourismKnowledgeToolAdapter

CORPUS_PATH = Path(__file__).parent / "knowledge_corpus" / "hangzhou_reviewed_v1.json"
_default_tool = None


def load_reviewed_documents() -> list[KnowledgeDocument]:
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return [KnowledgeDocument.model_validate(item) for item in payload["documents"]]


async def build_reviewed_knowledge_tool() -> TourismKnowledgeToolAdapter:
    repository = InMemoryKnowledgeRepository()
    ingestor = CuratedKnowledgeIngestor(repository)
    documents = load_reviewed_documents()
    for document in documents:
        await ingestor.ingest(document)
    return TourismKnowledgeToolAdapter(TourismKnowledgeService(repository),
        supported_destinations={document.destination for document in documents})


async def get_default_knowledge_tool() -> TourismKnowledgeToolAdapter:
    global _default_tool
    if _default_tool is None:
        # In-memory ingest has no external await/IO; publish only the complete
        # repository. The value contains no loop-bound DB/client connections.
        _default_tool = await build_reviewed_knowledge_tool()
    return _default_tool
