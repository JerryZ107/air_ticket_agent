#!/usr/bin/env python3
"""打印 QA：默认读取最近一次 ques 批量结果，并从 obs.chat_messages 拉取对话全文。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-backend"))

from db.pool import close_pool, get_pool, init_pool  # noqa: E402

DEFAULT_BATCH = ROOT / "eval" / "ques_batch_results.json"


def load_batch(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


async def fetch_thread_messages(thread_id: str) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT cm.sequence_no, cm.role, cm.content, cm.created_at,
                   cm.trace_id, u.username
            FROM obs.chat_messages cm
            JOIN public.users u ON u.id = cm.user_id
            WHERE cm.thread_id = $1
            ORDER BY cm.sequence_no
            """,
            thread_id,
        )
    return [dict(r) for r in rows]


async def fetch_recent_threads(limit: int) -> list[str]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT thread_id
            FROM obs.chat_messages
            WHERE thread_id <> 'pending'
            GROUP BY thread_id
            ORDER BY MAX(created_at) DESC
            LIMIT $1
            """,
            limit,
        )
    return [r["thread_id"] for r in rows]


def print_messages(qid: str, user: str, thread_id: str | None, messages: list[dict]) -> None:
    print(f"\n{'=' * 72}")
    print(f"[{qid}] user={user} thread={thread_id or '—'}")
    if not messages:
        print("  (obs.chat_messages 中无记录)")
        return
    for m in messages:
        role = m["role"]
        ts = m.get("created_at")
        trace = m.get("trace_id")
        head = f"  [{role}] seq={m['sequence_no']}"
        if ts:
            head += f" @ {ts}"
        if trace:
            head += f" trace={trace}"
        print(head)
        body = (m.get("content") or "").strip()
        for line in body.splitlines():
            print(f"    {line}")
        if not body:
            print("    (empty)")


def print_qa_block(
    qid: str,
    user: str,
    thread_id: str | None,
    question: str,
    messages: list[dict],
    json_reply: str | None,
    ok: bool,
) -> None:
    print(f"\n{'=' * 72}")
    print(f"[{qid}] user={user} thread={thread_id or '—'}")

    has_user_db = any(m.get("role") == "user" for m in messages)
    if question and not has_user_db:
        print("  [user]")
        for line in question.splitlines():
            print(f"    {line}")

    if messages:
        for m in messages:
            role = m["role"]
            ts = m.get("created_at")
            trace = m.get("trace_id")
            head = f"  [{role}] seq={m['sequence_no']}"
            if ts:
                head += f" @ {ts}"
            if trace:
                head += f" trace={trace}"
            print(head)
            body = (m.get("content") or "").strip()
            for line in body.splitlines():
                print(f"    {line}")
    elif ok and json_reply:
        print("  [assistant] (来自批量 JSON，obs 无记录)")
        for line in json_reply.splitlines():
            print(f"    {line}")
    elif not question and not messages:
        print("  (无对话记录)")

    # 批量 JSON 与库内 assistant 不一致时补一份对照（便于发现截断/漏记）
    if json_reply and messages:
        db_assistant = "\n".join(
            (m.get("content") or "").strip()
            for m in messages
            if m.get("role") == "assistant"
        ).strip()
        if db_assistant and json_reply.strip() != db_assistant and len(json_reply) > len(db_assistant) + 20:
            print("  [assistant] (批量 JSON 更长，补打)")
            for line in json_reply.splitlines():
                print(f"    {line}")


async def run_batch(batch_path: Path, id_filter: set[str] | None) -> None:
    data = load_batch(batch_path)
    if data is None:
        print(f"未找到批量结果: {batch_path}")
        print("将改为打印数据库中最近的对话线程。")
        await run_recent(10)
        return

    rows = data.get("results", [])
    if id_filter:
        rows = [r for r in rows if str(r.get("id", "")) in id_filter]

    print("## 批量 QA（来自 eval + obs.chat_messages）")
    print(f"- 文件: {batch_path}")
    print(f"- 开始: {data.get('started_at')}")
    print(f"- 结束: {data.get('finished_at')}")
    print(f"- 本批输出: {len(rows)} 条（过滤后）")

    printed_ids: list[str] = []
    for row in rows:
        qid = row.get("id", "?")
        printed_ids.append(qid)
        user = row.get("user", "?")
        thread_id = row.get("thread_id")
        question = (row.get("question") or "").strip()
        json_reply = (row.get("reply") or "").strip() or None
        messages = []
        if thread_id:
            messages = await fetch_thread_messages(thread_id)
        print_qa_block(qid, user, thread_id, question, messages, json_reply, row.get("ok"))

    print(f"\n## 已输出题号 ({len(printed_ids)}): {', '.join(printed_ids)}")
    if id_filter and not printed_ids:
        print(f"警告: 过滤 {id_filter} 未匹配到任何题目，请检查 eval 文件或题号。")


async def run_recent(limit: int) -> None:
    threads = await fetch_recent_threads(limit)
    print(f"## 最近 {len(threads)} 个 thread（obs.chat_messages）")
    for tid in threads:
        messages = await fetch_thread_messages(tid)
        user = messages[0]["username"] if messages else "?"
        print_messages(tid, user, tid, messages)


async def run_thread(thread_id: str) -> None:
    messages = await fetch_thread_messages(thread_id)
    print(f"## thread {thread_id}")
    print_messages(thread_id, messages[0]["username"] if messages else "?", thread_id, messages)


async def main() -> None:
    parser = argparse.ArgumentParser(description="打印 QA 对话记录")
    parser.add_argument(
        "--batch",
        type=Path,
        default=DEFAULT_BATCH,
        help="ques 批量结果 JSON（默认 eval/ques_batch_results.json）",
    )
    parser.add_argument(
        "--recent",
        type=int,
        metavar="N",
        help="不读批量文件，打印最近 N 个 thread",
    )
    parser.add_argument("--thread", dest="thread_id", help="指定 thread_id")
    parser.add_argument(
        "--id",
        nargs="*",
        metavar="QID",
        help="只打印指定题号，如: --id M07 A04",
    )
    args = parser.parse_args()

    id_filter = set(args.id) if args.id else None

    await init_pool()
    try:
        if args.thread_id:
            await run_thread(args.thread_id)
        elif args.recent is not None:
            await run_recent(args.recent)
        else:
            await run_batch(args.batch, id_filter)
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
