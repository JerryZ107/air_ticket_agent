#!/usr/bin/env python3
"""纯后端：登录 + /api/chat 或 tool_facade 直连对比。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-backend"))

import httpx  # noqa: E402

BASE = "http://127.0.0.1:8001"


async def facade_lists() -> None:
    from db.pool import close_pool, init_pool
    from db.repository.auth import auth_repo
    from db.repository.bookings import Actor
    from services.tool_facade import list_bookings

    await init_pool()
    try:
        for username in ("zhangsan", "admin"):
            print(f"\n=== tool_facade list_bookings ({username}) ===")
            print(await list_bookings(username))
    finally:
        await close_pool()


def api_chat(username: str, password: str, message: str) -> None:
    with httpx.Client(base_url=BASE, timeout=180.0) as client:
        r = client.post("/api/auth/login", json={"username": username, "password": password})
        print(f"\n=== /api/chat ({username}) ===")
        print("login:", r.status_code)
        if r.status_code != 200:
            print(r.text)
            return
        token = r.json().get("token")
        r2 = client.post(
            "/api/chat",
            json={"message": message},
            headers={"Authorization": f"Bearer {token}"},
        )
        print("chat:", r2.status_code)
        if r2.status_code == 200:
            data = r2.json()
            print("thread_id:", data.get("thread_id"))
            print("reply:\n", data.get("reply"))
        else:
            print(r2.text)


def main() -> None:
    print("--- 数据层（不经过 LLM）---")
    asyncio.run(facade_lists())

    print("\n--- Agent /api/chat（经过 LLM + 工具）---")
    api_chat("zhangsan", "demo123", "展示下我最近的订单")
    api_chat("admin", "demo123", "最近有什么订单")


if __name__ == "__main__":
    main()
