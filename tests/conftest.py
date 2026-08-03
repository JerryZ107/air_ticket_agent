"""Shared pytest fixtures: path setup and PostgreSQL availability guard."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python-backend"))

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://airline:airline@localhost:5432/airline",
)


def _db_reachable() -> bool:
    try:
        import asyncpg
    except ImportError:
        return False
    try:
        async def _probe() -> bool:
            conn = await asyncpg.connect(DATABASE_URL, timeout=2)
            await conn.close()
            return True

        return asyncio.run(_probe())
    except Exception:
        return False


@pytest.fixture(scope="session")
def requires_db() -> None:
    if not _db_reachable():
        pytest.skip("PostgreSQL not reachable; DB integration tests skipped")


@pytest.fixture(scope="module")
def db_pool(requires_db) -> None:
    """初始化全局连接池（幂等），测试结束关闭。"""
    from db.pool import close_pool, init_pool

    asyncio.run(init_pool())
    yield
    asyncio.run(close_pool())
