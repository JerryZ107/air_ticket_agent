"""RAG hybrid retrieval: 中文关键词 + BM25 + 向量；Rerank 融合。"""

from __future__ import annotations

import re
from uuid import UUID

from db.pool import get_pool
from rag.embeddings import embed_texts, vector_literal
from rag.rerank import rerank
from rag.text_utils import question_terms
from rag.types import RetrievedChunk

NOT_FOUND_ANSWER = (
    "【手册未收录】订票手册中未检索到与您问题直接相关的条款，无法确认。"
    "请换种问法或联系人工客服。请仅向客户转述此结论，勿猜测、勿补充行业常识。"
)

_MIN_CONFIDENCE = 0.22
_MIN_TERM_COVERAGE = 0.12


def _terms(question: str) -> list[str]:
    return question_terms(question)


def _term_coverage(question: str, content: str) -> float:
    terms = _terms(question)
    if not terms:
        return 0.0
    text = content.lower()
    hits = sum(1 for t in terms if t.lower() in text or t in content)
    return hits / len(terms)


async def _keyword_search(question: str, top_k: int) -> list[RetrievedChunk]:
    terms = _terms(question)
    if not terms:
        terms = [question.strip()[:20]]
    patterns = [f"%{t}%" for t in terms if t]
    pool = get_pool()
    if patterns:
        # 先用 SQL 粗筛命中任一词条的候选，避免把全表拉进 Python 打分
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, source_file, content
                FROM document_chunks
                WHERE content ILIKE ANY($1::text[])
                """,
                patterns,
            )
    else:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, source_file, content FROM document_chunks LIMIT 50"
            )
    scored: list[RetrievedChunk] = []
    for r in rows:
        content = r["content"]
        hits = sum(1 for t in terms if t in content or t.lower() in content.lower())
        if hits == 0:
            continue
        score = hits / len(terms)
        scored.append(
            RetrievedChunk(
                id=r["id"],
                source_file=r["source_file"],
                content=content,
                score=score,
                channel="keyword",
            )
        )
    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]


async def _bm25_search(question: str, top_k: int) -> list[RetrievedChunk]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, source_file, content,
                   ts_rank(content_tsv, plainto_tsquery('simple', $1)) AS score
            FROM document_chunks
            WHERE content_tsv @@ plainto_tsquery('simple', $1)
            ORDER BY score DESC
            LIMIT $2
            """,
            question,
            top_k,
        )
    return [
        RetrievedChunk(
            id=r["id"],
            source_file=r["source_file"],
            content=r["content"],
            score=float(r["score"] or 0),
            channel="bm25",
        )
        for r in rows
    ]


async def _vector_search(question: str, top_k: int) -> list[RetrievedChunk]:
    vectors = await embed_texts([question])
    if not vectors:
        return []
    lit = vector_literal(vectors[0])
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            has = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM document_chunks WHERE embedding IS NOT NULL LIMIT 1)"
            )
            if not has:
                return []
            rows = await conn.fetch(
                """
                SELECT id, source_file, content,
                       1 - (embedding <=> $1::vector) AS score
                FROM document_chunks
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                lit,
                top_k,
            )
    except Exception:
        return []
    return [
        RetrievedChunk(
            id=r["id"],
            source_file=r["source_file"],
            content=r["content"],
            score=float(r["score"] or 0),
            channel="vector",
        )
        for r in rows
    ]


def _merge_candidates(*lists: list[RetrievedChunk]) -> list[RetrievedChunk]:
    by_id: dict[UUID, RetrievedChunk] = {}
    for lst in lists:
        for c in lst:
            prev = by_id.get(c.id)
            if prev is None or c.score > prev.score:
                by_id[c.id] = c
            else:
                by_id[c.id] = RetrievedChunk(
                    prev.id,
                    prev.source_file,
                    prev.content,
                    max(prev.score, c.score),
                    f"{prev.channel}+{c.channel}",
                )
    merged = list(by_id.values())
    merged.sort(key=lambda x: x.score, reverse=True)
    return merged


async def hybrid_search(question: str, top_k: int = 10) -> list[RetrievedChunk]:
    kw = await _keyword_search(question, top_k)
    vec = await _vector_search(question, top_k)
    bm25 = await _bm25_search(question, top_k)
    merged = _merge_candidates(kw, vec, bm25)
    if merged:
        return merged[:top_k]
    pool = get_pool()
    q = question.strip()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, source_file, content, 0.15::float AS score
            FROM document_chunks
            WHERE content ILIKE '%' || $1 || '%'
            LIMIT $2
            """,
            q[:40],
            top_k,
        )
    return [
        RetrievedChunk(
            id=r["id"],
            source_file=r["source_file"],
            content=r["content"],
            score=float(r["score"]),
            channel="ilike",
        )
        for r in rows
    ]


async def rag_answer(question: str, top_k: int = 3) -> tuple[str, float, list[UUID], list[dict]]:
    pool_size = max(top_k * 4, 12)
    candidates = await hybrid_search(question, top_k=pool_size)
    if not candidates:
        return NOT_FOUND_ANSWER, 0.0, [], []

    top = rerank(question, candidates, top_k=top_k)
    if not top:
        return NOT_FOUND_ANSWER, 0.0, [], []

    confidence = top[0].score if top else 0.0
    coverage = _term_coverage(question, top[0].content)
    rerank_log = [
        {
            "id": str(c.id),
            "source": c.source_file,
            "score": round(c.score, 4),
            "channel": c.channel,
            "term_coverage": round(_term_coverage(question, c.content), 3),
        }
        for c in top
    ]

    if confidence < _MIN_CONFIDENCE and coverage < _MIN_TERM_COVERAGE:
        return NOT_FOUND_ANSWER, confidence, [], rerank_log

    body = "\n\n---\n\n".join(f"[{c.source_file}]\n{c.content}" for c in top)
    answer = (
        "【以下为 faq_lookup_tool 检索到的订票手册原文，回答客户时仅可据此陈述，不得增删数字与规则】\n\n"
        f"{body}"
    )
    return answer, min(confidence, 1.0), [c.id for c in top], rerank_log
