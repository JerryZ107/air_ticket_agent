"""Lightweight rerank: keyword overlap + retrieval score fusion."""

from __future__ import annotations

from rag.text_utils import question_terms
from rag.types import RetrievedChunk


def rerank(question: str, candidates: list[RetrievedChunk], top_k: int = 3) -> list[RetrievedChunk]:
    if not candidates:
        return []
    terms = question_terms(question)
    scored: list[tuple[float, RetrievedChunk]] = []
    for c in candidates:
        text = c.content
        overlap = sum(1 for t in terms if t in text or t.lower() in text.lower())
        bonus = 0.0
        if overlap and terms:
            bonus = overlap / len(terms)
        fused = c.score * 0.45 + bonus * 0.55
        scored.append((fused, RetrievedChunk(c.id, c.source_file, c.content, fused, c.channel)))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]
