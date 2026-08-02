#!/usr/bin/env python3
"""Index manuals and embed all chunks (BGE-M3 local)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-backend"))

from db.pool import close_pool, init_pool  # noqa: E402
from rag.indexer import embed_missing_chunks, index_manuals  # noqa: E402
from llm_config import EMBEDDING_MODEL  # noqa: E402


async def main() -> None:
    await init_pool()
    try:
        n = await index_manuals()
        emb = await embed_missing_chunks()
        print(f"chunks={n} newly_embedded={emb} model={EMBEDDING_MODEL}")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
