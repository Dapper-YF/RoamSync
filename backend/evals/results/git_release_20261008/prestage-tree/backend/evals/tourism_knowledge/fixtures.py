"""Artificial texts test retrieval, not historical or travel factual accuracy."""
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from app.tourism_knowledge.ingestion import CuratedKnowledgeIngestor
from app.tourism_knowledge.models import EmbeddingMetadata, KnowledgeDocument
from app.tourism_knowledge.repository import InMemoryKnowledgeRepository

NOW = datetime(2026, 9, 29, tzinfo=UTC)
ROOT = Path(__file__).parent


def load_documents() -> list[KnowledgeDocument]:
    return [KnowledgeDocument.model_validate(item) for item in json.loads((ROOT / "corpus.json").read_text(encoding="utf-8"))]


class DeterministicFixtureEmbedding:
    """Hand-authored semantic concepts, no API calls and no production quality claim."""
    descriptor = EmbeddingMetadata(provider="fixture", model="hand-authored-concepts", dimensions=9, version="v1")
    concepts = (
        ("历史", "苏轼", "南宋", "往昔", "history"),
        ("茶文化", "良渚", "文化", "culture"),
        ("城市空间", "旅游风格", "整体特点", "profile"),
        ("景区体验", "灵隐", "体验差异", "place experience"),
        ("游览策略", "步行策略", "博物馆", "strategy"),
        ("父母", "老人", "轻松", "长辈", "省体力", "senior"),
        ("秋天", "秋季", "秋意", "autumn"),
        ("生活化", "市井", "当地生活", "日常烟火", "lifestyle"),
    )

    async def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        vectors = []
        for text in texts:
            concepts = tuple(float(any(term in text.casefold() for term in terms)) for terms in self.concepts)
            vectors.append(concepts + (float(not any(concepts)),))
        return vectors


async def fixture_repository(provider=None) -> InMemoryKnowledgeRepository:
    repo = InMemoryKnowledgeRepository()
    ingestor = CuratedKnowledgeIngestor(repo, provider)
    for document in load_documents():
        await ingestor.ingest(document)
    return repo
