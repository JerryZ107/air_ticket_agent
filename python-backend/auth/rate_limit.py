"""登录失败限速（进程内滑动窗口）。

仅限单进程部署；多进程需换 Redis 等共享存储。
按 username + 客户端 IP 组合计数，避免一个用户的多 IP 尝试绕过后
依然受同一用户名维度的累积计数约束。
"""

from __future__ import annotations

import time
from collections import defaultdict

MAX_FAILURES = 5
WINDOW_SECONDS = 600
LOCK_SECONDS = 600

# key -> 失败时间戳列表（滑动窗口）
_failures: dict[str, list[float]] = defaultdict(list)
# key -> 锁定截止时间戳
_locked_until: dict[str, float] = {}


def _key(username: str, client_ip: str | None) -> str:
    return f"{username.strip().lower()}|{client_ip or 'unknown'}"


def is_locked(username: str, client_ip: str | None) -> bool:
    now = time.time()
    key = _key(username, client_ip)
    deadline = _locked_until.get(key, 0.0)
    if deadline and now < deadline:
        return True
    if deadline:
        _locked_until.pop(key, None)
        _failures.pop(key, None)
    return False


def register_failure(username: str, client_ip: str | None) -> None:
    now = time.time()
    key = _key(username, client_ip)
    window = _failures[key]
    window.append(now)
    # 只保留窗口内的时间戳
    while window and window[0] <= now - WINDOW_SECONDS:
        window.pop(0)
    if len(window) >= MAX_FAILURES:
        _locked_until[key] = now + LOCK_SECONDS


def reset(username: str, client_ip: str | None) -> None:
    key = _key(username, client_ip)
    _failures.pop(key, None)
    _locked_until.pop(key, None)
