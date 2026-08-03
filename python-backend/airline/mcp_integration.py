"""Agents SDK ↔ airline MCP server (stdio) wiring."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from agents.mcp import MCPServerStdio

if TYPE_CHECKING:
    from agents import Agent

    from airline.context import AirlineAgentChatContext

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# 默认关闭：MCP stdio 子进程按进程单例运行，会话身份只能来自进程级环境变量，
# 无法按请求绑定登录用户。多用户部署下必须走本地 function_tool 路径
# （写操作身份由 Agent 会话上下文绑定）。仅在单用户/本地调试时显式开启。
USE_MCP_TOOLS = os.getenv("AIRLINE_USE_MCP_TOOLS", "false").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def create_airline_mcp_server() -> MCPServerStdio:
    env = {**os.environ}
    env.setdefault("DATABASE_URL", "postgresql://airline:airline@localhost:5432/airline")
    return MCPServerStdio(
        name="airline-booking",
        params={
            "command": sys.executable,
            "args": ["-m", "mcp_server"],
            "cwd": str(BACKEND_ROOT),
            "env": env,
        },
        cache_tools_list=True,
        client_session_timeout_seconds=120,
    )


def attach_mcp_server(server: MCPServerStdio, agents: list[Agent[AirlineAgentChatContext]]) -> None:
    for agent in agents:
        agent.mcp_servers = [server]
