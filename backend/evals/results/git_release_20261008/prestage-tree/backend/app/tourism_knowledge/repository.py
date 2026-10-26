"""Small-corpus reference adapter. Not a persistent production database."""
from datetime import datetime
from typing import Sequence

from .interfaces import IndexedChunk
from .models import KnowledgeDocument, TourismKnowledgeRequest


def matches_filters(item: IndexedChunk, request: TourismKnowledgeRequest, *, now: datetime) -> bool:
    chunk = item.chunk
    return (
        (request.destination is None or chunk.destination == request.destination)
        and (request.place_id is None or chunk.place_id == request.place_id)
        and (not request.knowledge_types or chunk.knowledge_type in request.knowledge_types)
        and set(request.audience_tags).issubset(chunk.audience_tags)
        and set(request.season_tags).issubset(chunk.season_tags)
        and set(request.experience_tags).issubset(chunk.experience_tags)
        and chunk.language == request.language
        and (request.include_fixtures or chunk.source.source_type != "fixture")
        and (chunk.valid_until is None or chunk.valid_until > now)
    )


class InMemoryKnowledgeRepository:
    def __init__(self):
        self._documents: dict[str, KnowledgeDocument] = {}
        self._chunks: dict[str, tuple[IndexedChunk, ...]] = {}

    async def replace_document(self, document: KnowledgeDocument, chunks: Sequence[IndexedChunk]) -> None:
        if not chunks:
            raise ValueError("document must have at least one chunk")
        if len({item.chunk.id for item in chunks}) != len(chunks):
            raise ValueError("duplicate chunk identities")
        expected = document.model_dump(exclude={"id", "title", "content"})
        for index, item in enumerate(chunks):
            chunk = item.chunk
            if chunk.document_id != document.id or chunk.title != document.title or chunk.chunk_index != index:
                raise ValueError("document/chunk identity mismatch")
            actual = chunk.model_dump(include=set(expected))
            if actual != expected:
                raise ValueError("chunk provenance differs from document")
            if (item.vector is None) != (chunk.embedding is None):
                raise ValueError("vector and embedding descriptor must be provided together")
            if item.vector is not None:
                from .ranking import validate_vectors
                validate_vectors([item.vector], count=1, dimensions=chunk.embedding.dimensions)
        # No await between validation and replacement: a reader observes either version.
        self._documents[document.id] = document.model_copy(deep=True)
        self._chunks[document.id] = tuple(IndexedChunk(item.chunk.model_copy(deep=True),
                                                     tuple(item.vector) if item.vector is not None else None) for item in chunks)

    async def candidates(self, request: TourismKnowledgeRequest, *, now: datetime) -> tuple[IndexedChunk, ...]:
        return tuple(IndexedChunk(item.chunk.model_copy(deep=True), item.vector)
                     for key in sorted(self._chunks) for item in self._chunks[key]
                     if matches_filters(item, request, now=now))
