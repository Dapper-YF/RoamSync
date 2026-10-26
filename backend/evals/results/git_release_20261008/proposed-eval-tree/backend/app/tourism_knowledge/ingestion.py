"""Explicit curated ingest; no crawling, provider selection or network fetching."""
import hashlib
import re
from typing import Sequence

from .interfaces import EmbeddingProvider, IndexedChunk, KnowledgeRepository
from .models import KnowledgeChunk, KnowledgeDocument
from .ranking import validate_vectors


def chunk_document(document: KnowledgeDocument, *, max_characters: int = 700) -> tuple[KnowledgeChunk, ...]:
    if max_characters < 32:
        raise ValueError("chunk size must be at least 32 characters")
    metadata = document.model_dump(exclude={"id", "title", "content"})
    chunks = []
    headings: list[str] = []
    buffer = ""
    current_path: tuple[str, ...] = ()

    def flush():
        nonlocal buffer
        if not buffer.strip():
            buffer = ""
            return
        content = buffer.strip()
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        index = len(chunks)
        identity = hashlib.sha256(f"{document.id}\0{index}\0{digest}".encode()).hexdigest()
        chunks.append(KnowledgeChunk(**metadata, id=identity, document_id=document.id,
            title=document.title, chunk_index=index, content=content, approximate_size=len(content),
            heading_path=current_path, content_sha256=digest))
        buffer = ""

    for line in document.content.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush()
            level = len(heading.group(1))
            headings = headings[:level - 1] + [heading.group(2)]
            current_path = tuple(headings)
        # Hard upper bound even for a long single paragraph, without dropping text.
        remainder = line + "\n"
        while remainder:
            room = max_characters - len(buffer)
            buffer += remainder[:room]
            remainder = remainder[room:]
            if len(buffer) == max_characters:
                flush()
    flush()
    return tuple(chunks)


class CuratedKnowledgeIngestor:
    def __init__(self, repository: KnowledgeRepository, embedding_provider: EmbeddingProvider | None = None,
                 *, max_characters: int = 700):
        self.repository = repository
        self.embedding_provider = embedding_provider
        self.max_characters = max_characters

    async def ingest(self, document: KnowledgeDocument) -> Sequence[KnowledgeChunk]:
        chunks = chunk_document(document, max_characters=self.max_characters)
        vectors = None
        if self.embedding_provider is not None:
            descriptor = self.embedding_provider.descriptor
            vectors = validate_vectors(await self.embedding_provider.embed([chunk.content for chunk in chunks]),
                                       count=len(chunks), dimensions=descriptor.dimensions)
            chunks = tuple(chunk.model_copy(update={"embedding": descriptor}) for chunk in chunks)
        # Embedding failures leave the previous version intact.
        await self.repository.replace_document(document, [IndexedChunk(chunk, vectors[index] if vectors else None)
                                                          for index, chunk in enumerate(chunks)])
        return chunks
