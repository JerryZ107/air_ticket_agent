#!/usr/bin/env python3
"""E1 验收：RAG + 权限 + Saga（确认号不变）。"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-backend"))

from db.pool import close_pool, init_pool  # noqa: E402
from db.repository.auth import auth_repo  # noqa: E402
from db.repository.bookings import (  # noqa: E402
    DENY_CONFIRMATION_MSG,
    Actor,
    BookingRepository,
)
from db.repository.saga import RebookingSaga  # noqa: E402
from rag.retriever import hybrid_search  # noqa: E402
from rag.rerank import rerank  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
RAG_FILE = EVAL_DIR / "rag_golden.jsonl"
AUTH_FILE = EVAL_DIR / "auth_cases.jsonl"
SESSION_FILE = EVAL_DIR / "session_isolation.jsonl"
RECALL_AT = 3
RECALL_THRESHOLD = 0.85

booking_test_repo = BookingRepository()


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


async def _actor(username: str) -> Actor:
    row = await auth_repo.get_user_by_username(username)
    if row is None:
        raise RuntimeError(f"seed user missing: {username}")
    return Actor(id=row["id"], role=row["role"])


async def run_rag_eval() -> tuple[int, int]:
    cases = _load_jsonl(RAG_FILE)
    if not cases:
        print("rag_golden.jsonl empty or missing")
        return 0, 0
    hit = 0
    for case in cases:
        q = case["question"]
        expected_source = case.get("expected_source")
        must = case.get("must_contain", "")
        chunks = rerank(q, await hybrid_search(q, top_k=12), top_k=RECALL_AT)
        ok = False
        for c in chunks:
            if expected_source and c.source_file != expected_source:
                continue
            if must and must not in c.content:
                continue
            ok = True
            break
        if ok:
            hit += 1
        else:
            print(f"  RAG MISS: {q!r}")
    return hit, len(cases)


async def run_auth_eval() -> tuple[int, int]:
    cases = _load_jsonl(AUTH_FILE)
    hit = 0
    for case in cases:
        actor = await _actor(case["actor"])
        conf = case["confirmation"]
        expect = case["expect"]
        try:
            row = await booking_test_repo.get_booking_for_actor(actor, conf)
            if expect == "allow":
                ok = row is not None and row.confirmation_no.upper() == conf.upper()
            else:
                ok = False
        except PermissionError as exc:
            ok = expect == "deny" and DENY_CONFIRMATION_MSG in str(exc)
        except Exception:
            ok = False
        if ok:
            hit += 1
        else:
            print(f"  AUTH MISS: {case['id']} actor={case['actor']} expect={expect}")
    return hit, len(cases)


class _FakeUser:
    """Minimum user stub for MemoryStore ownership checks (only .id is used)."""

    def __init__(self, uid: str) -> None:
        self.id = uid


async def run_session_eval() -> tuple[int, int]:
    """会话隔离验收：thread 归属校验（纯内存，不依赖 DB / API key）。

    回归保护：跨用户访问他人 thread 必须视为"不存在"（NotFoundError），
    线程列表按 owner 过滤；无身份的内部调用保持放行。
    """
    from datetime import datetime

    from chatkit.store import NotFoundError
    from chatkit.types import ThreadMetadata

    from memory_store import MemoryStore

    cases = _load_jsonl(SESSION_FILE)
    if not cases:
        print("session_isolation.jsonl empty or missing")
        return 0, 0

    user_a = _FakeUser("user_a")
    user_b = _FakeUser("user_b")
    ctx_a = {"user": user_a}
    ctx_b = {"user": user_b}
    ctx_anon = {}

    hit = 0
    for case in cases:
        store = MemoryStore()  # 每个用例独立实例，无状态残留

        def thread() -> ThreadMetadata:
            return ThreadMetadata(
                id=f"thr_{len(store._threads)}_eval",
                created_at=datetime.now(),
            )

        cid = case["id"]
        owner_ctx = ctx_a if case["owner"] == "user_a" else ctx_b
        actor_ctx = {
            "user_a": ctx_a,
            "user_b": ctx_b,
            "anonymous": ctx_anon,
        }[case["actor"]]
        # 先由 owner 建一个 thread；再建一个"其他用户"的 thread 用于列表过滤
        t_own = thread()
        await store.save_thread(t_own, owner_ctx)
        other_user = user_b if case["owner"] == "user_a" else user_a
        await store.save_thread(thread(), {"user": other_user})

        action = case["action"]
        expect = case["expect"]
        try:
            if action == "load_thread":
                await store.load_thread(t_own.id, actor_ctx)
                result = "ok"
            elif action == "load_thread_items":
                await store.load_thread_items(t_own.id, None, 10, "desc", actor_ctx)
                result = "ok"
            elif action == "save_thread":
                await store.save_thread(t_own, actor_ctx)
                result = "ok"
            elif action == "load_threads":
                page = await store.load_threads(10, None, "desc", actor_ctx)
                ids = [x.id for x in page.data]
                if expect == "own_only":
                    result = "ok" if ids == [t_own.id] else f"got {ids}"
                elif expect == "not_listed":
                    result = "ok" if t_own.id not in ids else f"listed {t_own.id}"
                else:
                    result = "unexpected_expect"
            elif action == "delete_thread":
                await store.delete_thread(t_own.id, actor_ctx)
                result = "ok"
            else:
                result = f"unknown_action:{action}"
        except NotFoundError:
            result = "not_found"

        ok = (result == "ok" and expect in ("ok", "own_only", "not_listed")) or (
            result == "not_found" and expect == "not_found"
        )
        if ok:
            hit += 1
        else:
            print(f"  SESSION MISS: {cid} owner={case['owner']} actor={case['actor']} "
                  f"action={action} expect={expect} -> {result}")
    return hit, len(cases)


async def run_saga_eval() -> tuple[int, int]:
    """改签后确认号不变，并恢复原航班（避免污染 seed）。"""
    from uuid import uuid4

    from db.observability import obs_writer
    from pipeline.request_context import RequestContext, clear_request_context, set_request_context

    actor = await _actor("zhangsan")
    conf = "ABC123"
    before = await booking_test_repo.get_booking_for_actor(actor, conf)
    if before is None or before.status != "confirmed":
        print("  SAGA SKIP: ABC123 not confirmed (re-seed DB?)")
        return 0, 1
    snap_flight = before.flight_id
    snap_seat = before.seat
    trace_id = uuid4()
    set_request_context(
        RequestContext(trace_id=trace_id, user_id=actor.id, role=actor.role)
    )
    await obs_writer.start_trace(trace_id, actor.id, None, "/eval/saga")
    saga = RebookingSaga()
    try:
        msg = await saga.run(actor, conf, "NY900", "15A")
    finally:
        await obs_writer.end_trace(trace_id, "ok")
        clear_request_context()
    after = await booking_test_repo.get_booking_for_actor(actor, conf)
    ok = (
        after is not None
        and after.confirmation_no.upper() == conf.upper()
        and ("确认号" in msg or "不变" in msg or "NY900" in msg)
    )
    from db.pool import get_pool

    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE bookings SET flight_id = $2, seat = $3, status = 'confirmed', updated_at = now()
            WHERE UPPER(confirmation_no) = UPPER($1)
            """,
            conf,
            snap_flight,
            snap_seat,
        )
    if ok:
        return 1, 1
    print(f"  SAGA MISS: {msg!r}")
    return 0, 1


async def main() -> int:
    failed = False
    try:
        # 会话隔离不依赖 DB / API key，先跑（数据库不可用时仍可验收）
        sh, st = await run_session_eval()
        print(f"Session isolation: {sh}/{st}")
        if sh < st:
            failed = True

        await init_pool()
        hit, total = await run_rag_eval()
        rate = hit / total if total else 0.0
        print(f"RAG Recall@{RECALL_AT}: {hit}/{total} = {rate:.1%} (threshold {RECALL_THRESHOLD:.0%})")
        if rate < RECALL_THRESHOLD:
            failed = True

        ah, at = await run_auth_eval()
        print(f"Auth repository: {ah}/{at}")
        if ah < at:
            failed = True

        sh, st = await run_saga_eval()
        print(f"Saga (confirmation unchanged): {sh}/{st}")
        if sh < st:
            failed = True

        for name in ("tool_cases.jsonl", "saga_rollback.jsonl"):
            n = len(_load_jsonl(EVAL_DIR / name))
            print(f"  {name}: {n} cases (LLM E2E — manual demo)")

        return 1 if failed else 0
    finally:
        await close_pool()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
