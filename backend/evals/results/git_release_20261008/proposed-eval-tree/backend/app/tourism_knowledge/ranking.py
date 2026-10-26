"""Deterministic Chinese-aware lexical baseline and optional semantic ranking."""
import math
import re
import unicodedata
from collections import Counter
from typing import Sequence

from .interfaces import IndexedChunk


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text).casefold()
    tokens = re.findall(r"[a-z0-9]+", text)
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        tokens.extend(run)
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def lexical_rank(query: str, candidates: Sequence[IndexedChunk]) -> dict[str, float]:
    # Title appears twice; tags are filters, not artificial query expansion.
    counts = [Counter(tokenize(f"{item.chunk.title} {item.chunk.title} {item.chunk.content}")) for item in candidates]
    if not counts:
        return {}
    sizes = [sum(c.values()) for c in counts]
    average = sum(sizes) / len(sizes) or 1
    frequencies = Counter(term for c in counts for term in c)
    query_terms = set(tokenize(query))
    # Multi-character Chinese queries use bigrams to avoid accidental matches
    # on generic single characters (e.g. 体 in both 省体力 and 体验).
    if any(re.fullmatch(r"[\u3400-\u9fff]{2}", term) for term in query_terms):
        query_terms = {term for term in query_terms if not re.fullmatch(r"[\u3400-\u9fff]", term)}
    scores = {}
    for item, count, size in zip(candidates, counts, sizes):
        score = 0.0
        for term in query_terms:
            tf = count[term]
            if not tf:
                continue
            df = frequencies[term]
            idf = math.log(1 + (len(counts) - df + 0.5) / (df + 0.5))
            score += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * size / average))
        if score > 0:
            scores[item.chunk.id] = score
    return scores


def validate_vectors(vectors: Sequence[Sequence[float]], *, count: int, dimensions: int) -> tuple[tuple[float, ...], ...]:
    if len(vectors) != count:
        raise ValueError("embedding batch cardinality mismatch")
    validated = []
    for vector in vectors:
        values = tuple(float(value) for value in vector)
        if len(values) != dimensions or not all(math.isfinite(v) for v in values):
            raise ValueError("embedding dimension/non-finite value mismatch")
        # Stable norm avoids overflow in finite vectors with large coordinates.
        norm = math.hypot(*values)
        if not norm or not math.isfinite(norm):
            raise ValueError("embedding vector must have a finite non-zero norm")
        validated.append(values)
    return tuple(validated)


def semantic_rank(query_vector: tuple[float, ...], candidates: Sequence[IndexedChunk]) -> dict[str, float]:
    validate_vectors([query_vector], count=1, dimensions=len(query_vector))
    query_norm = math.hypot(*query_vector)
    scores = {}
    for item in candidates:
        if item.vector is None:
            continue
        validate_vectors([item.vector], count=1, dimensions=len(query_vector))
        norm = math.hypot(*item.vector)
        score = sum((a / query_norm) * (b / norm) for a, b in zip(query_vector, item.vector))
        if score > 0:
            scores[item.chunk.id] = min(score, 1.0)
    return scores


def reciprocal_rank_fusion(*rankings: dict[str, float], limit: int = 100, rank_constant: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        ordered = sorted(ranking, key=lambda key: (-ranking[key], key))[:limit]
        for position, key in enumerate(ordered, 1):
            scores[key] = scores.get(key, 0) + 1 / (rank_constant + position)
    return scores
