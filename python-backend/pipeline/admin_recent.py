"""管理员全库最近订单直答（Binder 已注入，绕过 Agent 与工具调用）。

入口 binder（preprocess_message）在 agent 运行前已把全库最近订单注入
state.bookings（admin 见全部用户最近 50 条）。本模块按规则命中
「最近/全部/列出订单」类问法后直接格式化注入数据，省一次 agent 轮次
与一次 list_bookings 工具调用，结果确定、无旁白。
"""

from __future__ import annotations

import re

from airline.context import AirlineAgentContext


_CUSTOMER_NAME_RE = re.compile(r"(?:旅客|用户|客户|乘客)\s*[a-zA-Z][a-zA-Z0-9_]*")


def is_admin_recent_orders(text: str) -> bool:
    """是否「管理员查全库最近/全部订单」类问法（指定旅客交给 admin_customer）。"""
    t = text.strip()
    if not t:
        return False
    # 本人订单不走此路径
    if "我" in t:
        return False
    # 指定旅客（旅客X/用户X…）交给 admin_customer；"旅客用户名"这类泛指不影响直答
    if _CUSTOMER_NAME_RE.search(t):
        return False
    return "订单" in t and any(k in t for k in ("最近", "列出", "全部", "全库", "列表"))


def format_admin_recent_orders(state: AirlineAgentContext) -> str | None:
    """格式化 Binder 注入的全库最近订单快照；无注入数据返回 None（由 Agent 兜底）。"""
    rows = state.bookings or []
    if not rows:
        return None
    lines: list[str] = []
    for b in rows:
        owner = f"旅客{b.get('owner_username')} " if b.get("owner_username") else ""
        lines.append(
            f"{owner}{b.get('confirmation_no')} {b.get('flight_no')} "
            f"{b.get('origin')}->{b.get('destination')} "
            f"座位{b.get('seat')} ({b.get('status')})"
        )
    return "最近订单列表：" + "；".join(lines)
