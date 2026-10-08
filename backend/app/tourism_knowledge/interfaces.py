"""Ports for persistence, ingestion, embedding and future Companion tool adapters."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence

from .models import EmbeddingMetadata, KnowledgeChunk, KnowledgeDocument, TourismKnowledgeRequest, TourismKnowledgeResult


@dataclass(frozen=True)
class IndexedChunk:
    chunk: KnowledgeChunk
    vector: tuple[float, ...] | None = None


class EmbeddingProvider(Protocol):
    @property
    def descriptor(self) -> EmbeddingMetadata: ...

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class KnowledgeRepository(Protocol):
    async def replace_document(self, document: KnowledgeDocument, chunks: Sequence[IndexedChunk]) -> None:
        """Atomically replace all versions of a document and its chunks."""
        ...

    async def candidates(self, request: TourismKnowledgeRequest, *, now: datetime) -> Sequence[IndexedChunk]:
        """Apply hard metadata, expiry and fixture filters BEFORE ranking."""
        ...


class KnowledgeIngestor(Protocol):
    async def ingest(self, document: KnowledgeDocument) -> Sequence[KnowledgeChunk]: ...


class TourismKnowledgeRetriever(Protocol):
    async def retrieve_tourism_knowledge(self, request: TourismKnowledgeRequest) -> TourismKnowledgeResult: ...
