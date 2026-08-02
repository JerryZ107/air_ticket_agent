#!/usr/bin/env python3
"""诊断 RAG 检索：问题 -> top chunks 是否含手册要点。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-backend"))

from db.pool import close_pool, init_pool  # noqa: E402
from rag.retriever import hybrid_search, rag_answer, NOT_FOUND_ANSWER  # noqa: E402
from services.tool_facade import faq_lookup  # noqa: E402

CASES = [
    ("R05", "自愿改签经济舱起飞前2小时以前的改期费是多少？", ["200", "30"]),
    ("R06", "能不能先退票再重新订票来代替改签？", ["勿", "不要", "先退"]),
    ("R11", "演示航线A320neo经济舱大概多少座？安全出口在第几排？", ["98", "4", "16"]),
    ("R14", "国内航班网上值机最早提前多久开放？柜台截止多久？", ["48", "45"]),
    (
        "M06",
        "行李额度是多少？如果延误3小时以上有什么餐券？",
        ["23", "50"],
    ),
]


async def main() -> None:
    await init_pool()
    try:
        for qid, q, needles in CASES:
            print(f"\n=== {qid} ===")
            print(f"Q: {q}")
            answer, conf, ids, log = await rag_answer(q)
            print(f"confidence={conf:.3f} chunks={len(ids)} not_found={NOT_FOUND_ANSWER[:20] in answer}")
            for row in log[:3]:
                print(f"  - {row}")
            top = await hybrid_search(q, top_k=3)
            for i, c in enumerate(top[:2], 1):
                snippet = c.content.replace("\n", " ")[:200]
                hits = [n for n in needles if n in c.content]
                print(f"  chunk{i} [{c.source_file}] score={c.score:.3f} hits={hits}")
                print(f"    {snippet}...")
        if qid == "M06":
            merged = await faq_lookup(q)
            print(f"faq_lookup(compound): not_found={NOT_FOUND_ANSWER[:20] in merged} len={len(merged)}")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
