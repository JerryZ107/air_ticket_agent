"""管理员查询指定旅客订单（代查），避免误走 FAQ「确认号」或误用确认号工具。"""

from __future__ import annotations

import re

from services import tool_facade as api

_CUSTOMER_RE = re.compile(
    r"(?:旅客|用户|客户|乘客)\s*([a-zA-Z][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)


def extract_customer_username(text: str) -> str | None:
    m = _CUSTOMER_RE.search(text.strip())
    if not m:
        return None
    return m.group(1).strip().lower()


def is_admin_customer_lookup(text: str) -> bool:
    """是否「查某旅客订单/确认号」类问法（非 FAQ 政策）。"""
    t = text.strip()
    if not extract_customer_username(t):
        return False
    return any(k in t for k in ("确认号", "订单", "查", "查询", "列表", "名下"))


async def answer_admin_customer_lookup(question: str, admin_username: str) -> str | None:
    """命中则返回基于 list_customer_bookings 的答复；否则 None。"""
    if not is_admin_customer_lookup(question):
        return None
    customer = extract_customer_username(question)
    if not customer:
        return None

    raw = await api.list_customer_bookings(admin_username, customer)
    if "未找到订单" in raw or "暂无" in raw:
        return f"系统中未查询到旅客 {customer} 的订单。"

    if "确认号" in question:
        return (
            f"已为您查询旅客 {customer} 的订单（仅依据系统返回）：\n{raw}\n"
            "如需办理退改签，请说明要操作的确认号。"
        )
    return raw
