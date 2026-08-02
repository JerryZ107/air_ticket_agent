"""Index docs/manual markdown into document_chunks."""

from __future__ import annotations

import re

from db.pool import get_pool

from rag.embeddings import embed_texts, vector_literal
from rag.paths import policy_manual_dir

MANUAL_DIR = policy_manual_dir()
CHUNK_MAX = 1000
_SKIP_INDEX = frozenset({"README.md"})


def _split_markdown(text: str, source_file: str) -> list[str]:
    """按一级标题 (# ) 切分；过长段落按空行再切，并带上文件名与标题前缀便于检索。"""
    sections = re.split(r"\n(?=# )", text.strip())
    chunks: list[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        first_line = section.split("\n", 1)[0].strip()
        prefix = f"[{source_file}] {first_line}\n"

        def emit(block: str) -> None:
            block = block.strip()
            if not block:
                return
            full = prefix + block if not block.startswith(prefix) else block
            if len(full) <= CHUNK_MAX:
                chunks.append(full)
                return
            paras = re.split(r"\n\n+", block)
            buf = prefix
            for para in paras:
                para = para.strip()
                if not para:
                    continue
                candidate = (buf + para) if buf != prefix else prefix + para
                if len(candidate) <= CHUNK_MAX:
                    buf = candidate if buf != prefix else candidate
                else:
                    if buf.strip() and buf != prefix:
                        chunks.append(buf.strip())
                    buf = prefix + para
                    while len(buf) > CHUNK_MAX:
                        chunks.append(buf[:CHUNK_MAX])
                        buf = prefix + buf[CHUNK_MAX - len(prefix) - 40 :]
            if buf.strip() and buf != prefix:
                chunks.append(buf.strip())

        emit(section)

    if not chunks and text.strip():
        chunks.append(f"[{source_file}]\n{text.strip()[:CHUNK_MAX]}")
    return chunks


async def index_manuals() -> int:
    pool = get_pool()
    count = 0
    if not MANUAL_DIR.exists():
        MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    async with pool.acquire() as conn:
        for path in sorted(MANUAL_DIR.glob("*.md")):
            if path.name in _SKIP_INDEX:
                continue
            text = path.read_text(encoding="utf-8")
            title = path.stem
            pieces = _split_markdown(text, path.name)
            await conn.execute(
                "DELETE FROM document_chunks WHERE source_file = $1",
                path.name,
            )
            for idx, chunk in enumerate(pieces):
                await conn.execute(
                    """
                    INSERT INTO document_chunks (source_file, chunk_index, title, content)
                    VALUES ($1, $2, $3, $4)
                    """,
                    path.name,
                    idx,
                    title,
                    chunk,
                )
                count += 1
    await embed_missing_chunks()
    return count


async def embed_missing_chunks() -> int:
    """为尚未生成向量的 chunk 调用 Embedding API（无 key 时跳过）。"""
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            col = await conn.fetchval(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'document_chunks' AND column_name = 'embedding'
                """
            )
        except Exception:
            return 0
        if not col:
            return 0
        rows = await conn.fetch(
            """
            SELECT id, content FROM document_chunks
            WHERE embedding IS NULL
            ORDER BY source_file, chunk_index
            """
        )
    if not rows:
        return 0
    texts = [r["content"] for r in rows]
    vectors = await embed_texts(texts)
    if len(vectors) != len(rows):
        return 0
    updated = 0
    async with pool.acquire() as conn:
        for row, vec in zip(rows, vectors):
            try:
                await conn.execute(
                    "UPDATE document_chunks SET embedding = $1::vector WHERE id = $2",
                    vector_literal(vec),
                    row["id"],
                )
                updated += 1
            except Exception:
                pass
    return updated
