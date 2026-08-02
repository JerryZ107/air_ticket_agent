"""Shared tool facade: repository + RAG (used by function_tool and MCP)."""

from __future__ import annotations

import json
import time
from uuid import UUID

from db.observability import obs_writer
from db.pool import get_pool, init_pool
from db.repository.auth import auth_repo
from db.repository.bookings import Actor, booking_repo
from db.repository.saga import RebookingSaga
from pipeline.request_context import RequestContext, get_request_context, set_request_context
from rag.retriever import rag_answer


def _format_booking_lines(rows: list) -> list[str]:
    lines: list[str] = []
    for b in rows:
        owner = f"旅客{b.owner_username} " if b.owner_username else ""
        lines.append(
            f"{owner}{b.confirmation_no} {b.flight_no} {b.origin}->{b.destination} "
            f"座位{b.seat} ({b.status})"
        )
    return lines


async def ensure_db() -> None:
    try:
        get_pool()
    except RuntimeError:
        await init_pool()


async def resolve_actor(username: str) -> Actor:
    await ensure_db()
    row = await auth_repo.get_user_by_username(username.strip())
    if row is None:
        raise ValueError(f"未知用户: {username}")
    return Actor(id=row["id"], role=row["role"])


async def faq_lookup(question: str) -> str:
    await ensure_db()
    t0 = time.time()
    answer, confidence, chunk_ids, rerank_log = await rag_answer(question)
    ms = int((time.time() - t0) * 1000)
    try:
        ctx = get_request_context()
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO obs.rag_queries (
                    trace_id, question, final_chunk_ids, top_confidence, latency_ms, reranked_hits
                )
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                """,
                ctx.trace_id,
                question,
                chunk_ids,
                confidence,
                ms,
                json.dumps(rerank_log),
            )
    except Exception:
        pass
    await _log_tool("faq_lookup", {"question": question}, answer, ms=ms)
    return answer


async def list_bookings(actor_username: str) -> str:
    actor = await resolve_actor(actor_username)
    rows = await booking_repo.list_bookings_for_actor(actor)
    if not rows:
        return "未找到订单。"
    out = "订单列表：" + "；".join(_format_booking_lines(rows))
    await _log_tool("list_bookings", {"session_user": actor_username}, out)
    return out


async def list_customer_bookings(admin_username: str, customer_username: str) -> str:
    admin = await resolve_actor(admin_username)
    try:
        rows = await booking_repo.list_bookings_for_customer(admin, customer_username.strip())
    except PermissionError as exc:
        out = str(exc)
        await _log_tool(
            "list_customer_bookings",
            {"admin": admin_username, "customer": customer_username},
            out,
            status="denied",
        )
        return out
    if not rows:
        return f"旅客 {customer_username} 未找到订单。"
    out = f"旅客 {customer_username} 订单：" + "；".join(_format_booking_lines(rows))
    await _log_tool(
        "list_customer_bookings",
        {"admin": admin_username, "customer": customer_username},
        out,
    )
    return out


async def flight_status(flight_number: str) -> str:
    await ensure_db()
    row = await booking_repo.get_flight_by_number(flight_number)
    if not row:
        return f"未找到航班 {flight_number}。"
    out = (
        f"航班 {row['flight_no']}（{row['origin']} 至 {row['destination']}）"
        f" | 状态：{row['status']}"
        f" | 出发 {row['departure_at']} -> 到达 {row['arrival_at']}"
        f" | 余票 {row['seats_available']}"
    )
    await _log_tool("flight_status", {"flight_number": flight_number}, out)
    return out


async def search_flights(origin: str | None = None, destination: str | None = None) -> str:
    await ensure_db()
    rows = await booking_repo.search_flights(origin, destination)
    if not rows:
        return "没有匹配的航班。"
    lines = [
        f"{r['flight_no']} {r['origin']} -> {r['destination']} "
        f"出发 {r['departure_at']} 余票 {r['seats_available']}"
        for r in rows
    ]
    out = "可选航班：\n" + "\n".join(lines)
    await _log_tool("search_flights", {"origin": origin, "destination": destination}, out)
    return out


async def cancel_booking(
    session_username: str,
    confirmation_number: str,
    on_behalf_of_username: str | None = None,
) -> str:
    actor = await resolve_actor(session_username)
    try:
        out = await booking_repo.cancel_booking(
            actor,
            confirmation_number,
            on_behalf_of_username=on_behalf_of_username,
        )
        await _log_tool(
            "cancel_booking",
            {
                "session_user": session_username,
                "confirmation_number": confirmation_number,
                "on_behalf_of_username": on_behalf_of_username,
            },
            out,
        )
        return out
    except PermissionError as exc:
        out = str(exc)
        await _log_tool(
            "cancel_booking",
            {
                "session_user": session_username,
                "confirmation_number": confirmation_number,
                "on_behalf_of_username": on_behalf_of_username,
            },
            out,
            status="denied",
        )
        return out


async def rebook_flight(
    session_username: str,
    confirmation_number: str,
    new_flight_number: str,
    new_seat: str = "自动分配",
    on_behalf_of_username: str | None = None,
) -> str:
    actor = await resolve_actor(session_username)
    saga = RebookingSaga()
    try:
        out = await saga.run(
            actor,
            confirmation_number,
            new_flight_number,
            new_seat,
            on_behalf_of_username=on_behalf_of_username,
        )
        await _log_tool(
            "rebook_flight",
            {
                "session_user": session_username,
                "confirmation_number": confirmation_number,
                "new_flight_number": new_flight_number,
                "on_behalf_of_username": on_behalf_of_username,
            },
            out,
        )
        return out
    except PermissionError as exc:
        out = str(exc)
        await _log_tool(
            "rebook_flight",
            {"confirmation_number": confirmation_number},
            out,
            status="denied",
        )
        return out


async def update_seat(
    session_username: str,
    confirmation_number: str,
    new_seat: str,
    on_behalf_of_username: str | None = None,
) -> str:
    actor = await resolve_actor(session_username)
    try:
        out = await booking_repo.update_seat(
            actor,
            confirmation_number,
            new_seat,
            on_behalf_of_username=on_behalf_of_username,
        )
        await _log_tool(
            "update_seat",
            {
                "session_user": session_username,
                "confirmation_number": confirmation_number,
                "new_seat": new_seat,
                "on_behalf_of_username": on_behalf_of_username,
            },
            out,
        )
        return out
    except PermissionError as exc:
        out = str(exc)
        await _log_tool(
            "update_seat",
            {"confirmation_number": confirmation_number},
            out,
            status="denied",
        )
        return out


def bind_mcp_actor(username: str, role: str, user_id: UUID | None = None) -> None:
    """Optional: set observability context for MCP tool calls."""
    from uuid import uuid4

    uid = user_id or uuid4()
    set_request_context(RequestContext(trace_id=uuid4(), user_id=uid, username=username, role=role))


async def _log_tool(name: str, inp: dict, out: str, *, status: str = "ok", ms: int | None = None) -> None:
    try:
        ctx = get_request_context()
        await obs_writer.log_tool_call(
            ctx.trace_id,
            name,
            inp,
            {"result": out},
            status=status,
            latency_ms=ms,
        )
    except Exception:
        pass
