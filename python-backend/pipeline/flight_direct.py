"""航班状态直连：规则可确定的查询绕过 Agent，直接基于工具结果回答。

与 faq_direct 同一哲学：确定性问题走确定性路径（省 token、无旁白、结果稳定），
需要后续操作（改签/退票等）时再由 Agent 接手。
"""

from __future__ import annotations

import re
from typing import Final

from services import tool_facade as api

_FLIGHT_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Z]{2}\s?\d{2,4})(?![A-Za-z0-9])",
    re.IGNORECASE,
)

_STATUS_ZH: Final[dict[str, str]] = {
    "scheduled": "计划中（正常）",
    "delayed": "延误",
    "cancelled": "已取消",
    "departed": "已起飞",
}


def _zh_status(raw: str) -> str:
    return re.sub(
        r"状态：(\w+)",
        lambda m: f"状态：{_STATUS_ZH.get(m.group(1), m.group(1))}",
        raw,
    )


async def answer_flight_status(question: str) -> str | None:
    """命中航班号则基于 flight_status 工具结果直接回答；未命中返回 None 交回 Agent。"""
    m = _FLIGHT_RE.search(question)
    if not m:
        return None
    flight_no = re.sub(r"\s+", "", m.group(1)).upper()
    raw = await api.flight_status(flight_no)
    if raw.startswith("未找到航班"):
        return None
    # 工具结果已经是事实文本；仅做轻量排版，不引入模型旁白
    return _zh_status(raw).replace(" | ", "\n")
