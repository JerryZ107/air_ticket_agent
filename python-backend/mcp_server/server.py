"""B 阶段 MCP Server：工具名与 Agent 对齐，内部走 services.tool_facade。"""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

from db.observability import obs_writer
from db.pool import close_pool, init_pool
from pipeline.request_context import RequestContext, set_request_context
from services import tool_facade as api

mcp = FastMCP(
    "airline-booking",
    instructions=(
        "航班订票助理 MCP。订单与写操作绑定 AIRLINE_SESSION_USERNAME（或调试 AIRLINE_MCP_ACTOR），"
        "工具参数中不可指定他人用户名。"
    ),
)


async def _with_trace(actor_username: str, path: str):
    from db.repository.auth import auth_repo

    await api.ensure_db()
    row = await auth_repo.get_user_by_username(actor_username.strip())
    if row is None:
        raise ValueError(f"未知用户: {actor_username}")
    trace_id = uuid4()
    set_request_context(
        RequestContext(
            trace_id=trace_id,
            user_id=row["id"],
            username=row["username"],
            role=row["role"],
        )
    )
    await obs_writer.start_trace(trace_id, row["id"], None, path)
    return trace_id


async def _end_trace(trace_id, status: str = "ok") -> None:
    await obs_writer.end_trace(trace_id, status)


def _session_username() -> str:
    """MCP 独立进程：优先 AIRLINE_SESSION_USERNAME，否则 AIRLINE_MCP_ACTOR（本地调试）。"""
    u = (os.getenv("AIRLINE_SESSION_USERNAME") or os.getenv("AIRLINE_MCP_ACTOR") or "").strip()
    if not u:
        raise ValueError("缺少会话用户：设置 AIRLINE_SESSION_USERNAME 或 AIRLINE_MCP_ACTOR")
    return u


@mcp.tool()
async def cancel_flight(
    confirmation_number: str,
    on_behalf_of_username: str | None = None,
) -> str:
    """取消订单；会话身份绑定 AIRLINE_SESSION_USERNAME，管理员代客目标经校验后绑定。"""
    user = _session_username()
    trace_id = await _with_trace(user, "/mcp/cancel_flight")
    try:
        return await api.cancel_booking(user, confirmation_number, on_behalf_of_username=on_behalf_of_username)
    finally:
        await _end_trace(trace_id)


@mcp.tool()
async def rebook_flight(
    confirmation_number: str,
    new_flight_number: str,
    new_seat: str = "自动分配",
    on_behalf_of_username: str | None = None,
) -> str:
    """改签（确认号不变）；会话身份绑定 AIRLINE_SESSION_USERNAME，管理员代客目标经校验后绑定。"""
    user = _session_username()
    trace_id = await _with_trace(user, "/mcp/rebook_flight")
    try:
        return await api.rebook_flight(
            user,
            confirmation_number,
            new_flight_number,
            new_seat,
            on_behalf_of_username=on_behalf_of_username,
        )
    finally:
        await _end_trace(trace_id)


@mcp.tool()
async def update_seat(
    confirmation_number: str,
    new_seat: str,
    on_behalf_of_username: str | None = None,
) -> str:
    """更新座位；会话身份绑定 AIRLINE_SESSION_USERNAME，管理员代客目标经校验后绑定。"""
    user = _session_username()
    trace_id = await _with_trace(user, "/mcp/update_seat")
    try:
        return await api.update_seat(
            user, confirmation_number, new_seat, on_behalf_of_username=on_behalf_of_username
        )
    finally:
        await _end_trace(trace_id)


def main() -> None:
    asyncio.run(init_pool())
    transport = os.getenv("AIRLINE_MCP_TRANSPORT", "stdio")
    try:
        mcp.run(transport=transport)
    finally:
        asyncio.run(close_pool())


if __name__ == "__main__":
    main()
