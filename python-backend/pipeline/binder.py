"""请求入口预处理（Binder）：在 Agent 运行前把会话身份与数据边界固化到 context。

设计原则：
- 登录用户：无条件注入全部订单快照 + 主订单。数据边界靠「注入」实现，
  而不是靠 prompt 要求模型「记得先查数据」——模型拿到的数据天然只有本人可见；
- admin 代客：从消息中确定性提取旅客用户名并预绑定，写操作工具自动以该旅客身份执行；
- 未登录演示：按城市关键词预选场景并注入行程，替代「让模型先调用工具填充」的 prompt。
"""

from __future__ import annotations

import re

from airline.context import AirlineAgentContext
from airline.demo_data import apply_itinerary_defaults
from airline.hydrate import actor_from_state, apply_booking_row
from db.repository.bookings import booking_repo

_CUSTOMER_RE = re.compile(
    r"(?:旅客|用户|客户|乘客)\s*([a-zA-Z][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)

_CITY_SCENARIO_KEYWORDS = ("paris", "new york", "austin", "巴黎", "纽约", "奥斯汀")


def extract_on_behalf_of_username(text: str) -> str | None:
    """从消息中确定性提取「旅客X」类目标用户名（与 admin_customer 同一规则）。"""
    m = _CUSTOMER_RE.search(text.strip())
    return m.group(1).strip().lower() if m else None


def select_demo_scenario(text: str) -> str:
    """未登录演示路径：按城市关键词预选场景（替代 prompt 里的城市关键词指令）。"""
    low = text.lower()
    return "disrupted" if any(k in low for k in _CITY_SCENARIO_KEYWORDS) else "on_time"


def _snapshot(rows) -> list[dict[str, str]]:
    return [
        {
            "confirmation_no": r.confirmation_no,
            "flight_no": r.flight_no or "",
            "origin": r.origin or "",
            "destination": r.destination or "",
            "seat": r.seat,
            "status": r.status,
            "owner_username": r.owner_username or "",
        }
        for r in rows
    ]


async def hydrate_user_data(state: AirlineAgentContext) -> None:
    """登录用户：注入全部订单快照，并把第一条作为主订单写入上下文。"""
    actor = actor_from_state(state)
    if actor is None:
        return
    if state.user_role == "admin" and state.on_behalf_of_username:
        rows = await booking_repo.list_bookings_for_customer(
            actor, state.on_behalf_of_username
        )
    else:
        rows = await booking_repo.list_bookings_for_actor(actor)
    state.bookings = _snapshot(rows)
    if rows:
        apply_booking_row(state, rows[0])


async def preprocess_message(state: AirlineAgentContext, user_text: str) -> None:
    """Agent 运行前统一预处理（binder）：身份提取 -> 数据注入。"""
    # 1) admin 代客目标预提取（先于数据注入，决定按谁的数据加载）
    if state.user_role == "admin":
        extracted = extract_on_behalf_of_username(user_text)
        if extracted:
            state.on_behalf_of_username = extracted

    # 2) 登录用户：注入订单数据；未登录演示：按关键词注入演示行程
    if state.user_id:
        await hydrate_user_data(state)
    else:
        apply_itinerary_defaults(state, scenario_key=select_demo_scenario(user_text))
